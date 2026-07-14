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

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .preprocessing import split_sentences, clean_text

FLAG_THRESHOLD = 0.55  # cosine similarity above this -> sentence flagged
HIGH_RISK_THRESHOLD = 0.75


@dataclass
class SentenceMatch:
    sentence: str
    best_score: float
    best_source: str
    best_source_sentence: str
    flagged: bool
    risk: str  # "low" | "medium" | "high"


@dataclass
class SimilarityReport:
    overall_score: float
    verdict: str
    sentence_matches: list[SentenceMatch] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)


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

    if not ref_sentence_records:
        return SimilarityReport(
            overall_score=0.0, verdict="LOW",
            sentence_matches=[
                SentenceMatch(s, 0.0, "-", "-", False, "low") for s in target_sentences
            ],
        )

    corpus_texts = target_sentences + [s for _, s in ref_sentence_records]
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(corpus_texts)

    n_target = len(target_sentences)
    target_vecs = tfidf_matrix[:n_target]
    ref_vecs = tfidf_matrix[n_target:]

    sim_matrix = cosine_similarity(target_vecs, ref_vecs)  # (n_target, n_ref)

    matches: list[SentenceMatch] = []
    flagged_count = 0
    score_accum = 0.0

    for i, sentence in enumerate(target_sentences):
        row = sim_matrix[i]
        best_j = int(row.argmax()) if row.size else -1
        best_score = float(row[best_j]) if best_j >= 0 else 0.0
        best_source, best_sentence = ref_sentence_records[best_j] if best_j >= 0 else ("-", "-")

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
            )
        )

    # Overall score blends: proportion of flagged sentences + mean similarity,
    # weighted so a handful of near-identical sentences move the needle like
    # a real similarity-report tool (e.g. Turnitin-style overall index).
    flagged_ratio = flagged_count / len(target_sentences)
    mean_sim = score_accum / len(target_sentences)
    overall = round(min(100.0, (0.65 * flagged_ratio + 0.35 * mean_sim) * 100), 1)

    return SimilarityReport(
        overall_score=overall,
        verdict=_verdict(overall),
        sentence_matches=matches,
        sources_used=sorted(reference_corpus.keys()),
    )
