"""
ML Component: TF-IDF + Cosine Similarity
=========================================
This is the core plagiarism-scoring engine described in the project
(Slide 6). It is intentionally implemented with scikit-learn's
TfidfVectorizer (not a wrapped external API) so the whole pipeline runs
fully offline, as required by the problem statement (Slide 5, 7).

Two levels of comparison are produced:
  1. Document-level score  -> overall plagiarism percentage
  2. Sentence-level scores -> which exact sentences are flagged + against
     which source, powering the "explainable" requirement (Slide 5) and
     the Correction Agent (Slide 13).
"""
from dataclasses import dataclass, field
import logging
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .preprocessing import split_sentences, clean_text
from .semantic_similarity import semantic_similarity_matrix
from ..settings import ENABLE_SEMANTIC_SIMILARITY

FLAG_THRESHOLD = 0.20  # hybrid similarity at or above this -> review flag
HIGH_RISK_THRESHOLD = 0.75
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class SentenceMatch:
    sentence: str
    best_score: float
    best_source: str
    best_source_sentence: str
    flagged: bool
    risk: str  # "low" | "medium" | "high"
    tfidf_score: float = 0.0
    cosine_score: float = 0.0
    semantic_score: float = 0.0
    hybrid_score: float = 0.0
    start_offset: int = 0
    end_offset: int = 0


@dataclass
class SimilarityReport:
    overall_score: float
    verdict: str
    sentence_matches: list[SentenceMatch] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    semantic_enabled: bool = False
    semantic_available: bool = False


def _risk_label(score: float) -> str:
    if score >= HIGH_RISK_THRESHOLD:
        return "high"
    if score >= FLAG_THRESHOLD:
        return "medium"
    return "low"


def _verdict(pct: float) -> str:
    if pct >= 70:
        return "HIGH"
    if pct >= 35:
        return "MODERATE"
    return "LOW"


def analyze_document(
    target_text: str,
    reference_corpus: dict[str, str],
) -> SimilarityReport:
    """
    target_text: the submitted report's text
    reference_corpus: {source_name: source_text} to compare against
                       (bundled sample papers + previously submitted reports)
    """
    target_sentences = split_sentences(target_text)
    # Keep offsets in the extracted document, not in a rewritten copy.  The
    # scoring input remains the existing normalized sentence list.
    sentence_offsets = _sentence_offsets(target_text, target_sentences)
    if not target_sentences:
        return SimilarityReport(overall_score=0.0, verdict="LOW")

    # Build one combined corpus: target sentences + every reference sentence,
    # each tagged with its source, so TF-IDF's IDF weighting reflects the
    # whole comparison universe rather than a single pair at a time.
    ref_sentence_records: list[tuple[str, str]] = []  # (source_name, sentence)
    for src_name, src_text in reference_corpus.items():
        for s in split_sentences(src_text):
            if len(s.split()) >= 4:
                ref_sentence_records.append((src_name, s))
    logger.info("Sentence splitting: upload=%d, references=%d, sources=%d", len(target_sentences), len(ref_sentence_records), len(reference_corpus))

    if not ref_sentence_records:
        return SimilarityReport(
            overall_score=0.0, verdict="LOW",
            sentence_matches=[
                SentenceMatch(
                    s, 0.0, "-", "-", False, "low",
                    start_offset=sentence_offsets[index][0],
                    end_offset=sentence_offsets[index][1],
                )
                for index, s in enumerate(target_sentences)
            ],
        )

    corpus_texts = target_sentences + [s for _, s in ref_sentence_records]
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        norm=None
    )
    tfidf_matrix = vectorizer.fit_transform(corpus_texts)
    logger.info("TF-IDF: vocabulary=%d, matrix=%s", len(vectorizer.vocabulary_), tfidf_matrix.shape)

    n_target = len(target_sentences)
    target_vecs = tfidf_matrix[:n_target]
    ref_vecs = tfidf_matrix[n_target:]

    cosine_matrix = cosine_similarity(target_vecs, ref_vecs)  # (n_target, n_ref)

    # This weighted TF-IDF overlap is distinct from cosine normalization: it
    # captures how much of a target sentence's TF-IDF signal appears in a
    # source sentence. Together with cosine and SBERT it forms the hybrid score.
    # True directional TF-IDF overlap.
    # Measures how much of the target sentence's TF-IDF weight
    # is covered by the reference sentence.
    tfidf_overlap_matrix = _tfidf_overlap(target_vecs, ref_vecs)

    print(
        "TF-IDF overlap: median=%.4f p95=%.4f max=%.4f"
        % (
            float(np.median(tfidf_overlap_matrix)),
            float(np.percentile(tfidf_overlap_matrix, 95)),
            float(tfidf_overlap_matrix.max()),
          )
    )

    print(
        "Cosine: median=%.4f p95=%.4f max=%.4f"
        % (
            float(np.median(cosine_matrix)),
            float(np.percentile(cosine_matrix, 95)),
            float(cosine_matrix.max()),
          )
   )
   

    semantic_matrix = (
        semantic_similarity_matrix(
            target_sentences,
            [s for _, s in ref_sentence_records]
        )
        if ENABLE_SEMANTIC_SIMILARITY
        else None
    )

    if semantic_matrix is not None:
        print(
            "SBERT: median=%.4f p95=%.4f max=%.4f"
            % (
                float(np.median(semantic_matrix)),
                float(np.percentile(semantic_matrix, 95)),
                float(semantic_matrix.max()),
            )
        )

    # When the optional model is disabled/unavailable, preserve the existing
    # lexical cosine result exactly as the fallback score.
    hybrid_matrix = (
        (
            0.35 * tfidf_overlap_matrix +
            0.35 * cosine_matrix +
            0.30 * semantic_matrix
        )
        if semantic_matrix is not None
        else (
            0.5 * tfidf_overlap_matrix +
            0.5 * cosine_matrix
        )
    )

    print(
        "HYBRID: median=%.4f p95=%.4f max=%.4f"
        % (
            float(np.median(hybrid_matrix)),
            float(np.percentile(hybrid_matrix, 95)),
            float(hybrid_matrix.max()),
        )
    )

    highest_target, highest_reference = np.unravel_index(
        int(hybrid_matrix.argmax()),
        hybrid_matrix.shape,
    )

    print(
        "HIGHEST PAIR: source=%s tfidf=%.4f cosine=%.4f sbert=%s hybrid=%.4f"
        % (
            ref_sentence_records[highest_reference][0],
            float(tfidf_overlap_matrix[highest_target, highest_reference]),
            float(cosine_matrix[highest_target, highest_reference]),
            (
                "%.4f" % semantic_matrix[highest_target, highest_reference]
                if semantic_matrix is not None
                else "disabled"
            ),
            float(hybrid_matrix[highest_target, highest_reference]),
        )
   )

    matches: list[SentenceMatch] = []
    flagged_count = 0
    score_accum = 0.0

    for i, sentence in enumerate(target_sentences):
        row = hybrid_matrix[i]
        best_j = int(row.argmax()) if row.size else -1
        best_score = float(row[best_j]) if best_j >= 0 else 0.0

        print(
            f"SENTENCE {i + 1}: "
            f"hybrid={best_score:.4f} "
            f"tfidf={float(tfidf_overlap_matrix[i, best_j]):.4f} "
            f"cosine={float(cosine_matrix[i, best_j]):.4f} "
            f"sbert={float(semantic_matrix[i, best_j]) if semantic_matrix is not None else 0.0:.4f}"
   )
  
        best_source, best_sentence = (
            ref_sentence_records[best_j]
            if best_j >= 0
            else ("-", "-")
        )

        tfidf_score = (
            float(tfidf_overlap_matrix[i, best_j])
            if best_j >= 0
            else 0.0
        )

        cosine_score = (
            float(cosine_matrix[i, best_j])
            if best_j >= 0
            else 0.0
        )

        semantic_score = (
            float(semantic_matrix[i, best_j])
            if semantic_matrix is not None and best_j >= 0
            else 0.0
        )

        flagged = best_score >= FLAG_THRESHOLD

        if flagged:
            flagged_count += 1

        score_accum += best_score

        matches.append(
            SentenceMatch(
                sentence=sentence,
                best_score=round(best_score * 100, 1),
                best_source=best_source,
                best_source_sentence=best_sentence,
                flagged=flagged,
                risk=_risk_label(best_score),
                tfidf_score=round(tfidf_score * 100, 1),
                cosine_score=round(cosine_score * 100, 1),
                semantic_score=round(semantic_score * 100, 1),
                hybrid_score=round(best_score * 100, 1),
                start_offset=sentence_offsets[i][0],
                end_offset=sentence_offsets[i][1],
            )
        )

    # Overall plagiarism/similarity score:
    # Consider the similarity of all sentences, while giving
    # additional weight to sentences that cross the plagiarism threshold.

    mean_similarity = (
        sum(match.hybrid_score / 100.0 for match in matches)
        / len(matches)
        if matches
        else 0.0
    )

    flagged_percentage = (
        flagged_count / len(target_sentences)
        if target_sentences
        else 0.0
    )

    overall = round(
        (
            mean_similarity * 0.90
            + flagged_percentage * 0.10
        ) * 100,
        1,
   )

    return SimilarityReport(
        overall_score=overall,
        verdict=_verdict(overall),
        sentence_matches=matches,
        sources_used=sorted(reference_corpus.keys()),
        semantic_enabled=ENABLE_SEMANTIC_SIMILARITY,
        semantic_available=semantic_matrix is not None,
    )


def _tfidf_overlap(target_vecs, ref_vecs) -> np.ndarray:
    """Compute the same directional overlap without dense vocabulary matrices."""
    result = np.zeros((target_vecs.shape[0], ref_vecs.shape[0]), dtype=np.float32)
    for i in range(target_vecs.shape[0]):
        target = target_vecs.getrow(i)
        total = float(target.data.sum())
        if total == 0:
            continue
        # Only features present in the target can contribute to the minimum.
        shared = ref_vecs[:, target.indices].tocoo()
        weights = np.minimum(shared.data, target.data[shared.col])
        result[i] = np.bincount(shared.row, weights=weights,
                                minlength=ref_vecs.shape[0]) / total
    return result


def _sentence_offsets(source_text: str, sentences: list[str]) -> list[tuple[int, int]]:
    """Map normalized analysis sentences back to exact extracted-text spans.

    Whitespace is allowed to differ because PDF and DOCX extraction can insert
    line breaks inside a sentence.  Each search starts after the preceding
    match, so duplicate sentences always retain their individual occurrence.
    """
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for sentence in sentences:
        parts = [part for part in sentence.split() if part]
        # PDF extraction can split a word with a hyphen and newline; clean_text
        # joins it for analysis, but offsets must still span the original bytes.
        pattern = r"\s+".join(
            r"(?:-\r?\n)?".join(re.escape(char) for char in part)
            for part in parts
        )
        match = re.search(pattern, source_text[cursor:], re.DOTALL)
        if not match:
            # This is defensive for unusual extraction artifacts; valid offsets
            # are still required before a correction can be applied.
            offsets.append((cursor, cursor))
            continue
        start = cursor + match.start()
        end = cursor + match.end()
        offsets.append((start, end))
        cursor = end
    return offsets
