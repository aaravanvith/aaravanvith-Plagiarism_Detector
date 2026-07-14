"""
Text preprocessing utilities.

Kept dependency-free (no nltk downloads) on purpose: the project brief
(Slide 5 / 7) requires an OFFLINE-CAPABLE detector with no internet
dependency, so we avoid nltk.download() calls that would fail without
network access at grading time.
"""
import re
from dataclasses import dataclass

STOPWORDS = set("""
a an the is are was were be been being to of in on for with and or but if
this that these those it its as at by from up down out about into over
after before between during under again further then once here there
when where why how all any both each few more most other some such no
nor not only own same so than too very s t can will just don should now
we our you your they their he she his her i my me
""".split())

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_WORD_RE = re.compile(r"[A-Za-z']+")


def clean_text(text: str) -> str:
    """Normalize whitespace, strip control chars, fix common PDF artifacts."""
    text = text.replace("\x0c", " ").replace("\u000b", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    # de-hyphenate line-wrapped words e.g. "inter-\nnet" -> "internet"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = text.replace("\n", " ")
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Lightweight rule-based sentence splitter (no punkt download required)."""
    text = clean_text(text)
    if not text:
        return []
    raw = _SENT_SPLIT_RE.split(text)
    sentences = [s.strip() for s in raw if len(s.strip()) > 0]
    # merge very short fragments (< 4 words) into the previous sentence
    merged: list[str] = []
    for s in sentences:
        if merged and len(s.split()) < 4:
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def content_words(text: str) -> list[str]:
    return [w for w in tokenize(text) if w not in STOPWORDS and len(w) > 1]


@dataclass
class DocStats:
    word_count: int
    sentence_count: int
    avg_sentence_len: float
    avg_word_len: float
    type_token_ratio: float
    stopword_ratio: float
    sentence_len_stdev: float
    punctuation_variety: int


def compute_doc_stats(text: str) -> DocStats:
    import statistics as st

    sentences = split_sentences(text)
    words = tokenize(text)
    n_words = max(len(words), 1)
    sent_lens = [len(tokenize(s)) for s in sentences] or [0]
    sw_count = sum(1 for w in words if w in STOPWORDS)
    unique = len(set(words))
    punctuation_variety = len(set(re.findall(r"[,;:\-\u2014()\"']", text)))

    return DocStats(
        word_count=n_words,
        sentence_count=max(len(sentences), 1),
        avg_sentence_len=sum(sent_lens) / max(len(sent_lens), 1),
        avg_word_len=sum(len(w) for w in words) / n_words,
        type_token_ratio=unique / n_words,
        stopword_ratio=sw_count / n_words,
        sentence_len_stdev=st.pstdev(sent_lens) if len(sent_lens) > 1 else 0.0,
        punctuation_variety=punctuation_variety,
    )
