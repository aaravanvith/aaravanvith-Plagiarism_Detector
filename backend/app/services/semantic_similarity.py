"""Optional SBERT semantic-similarity adapter.

The model is loaded only when semantic scoring is enabled and first needed.
If it cannot be loaded, callers receive ``None`` and can retain the legacy
TF-IDF workflow rather than failing an upload.
"""
from __future__ import annotations

import logging
import threading
from time import perf_counter
from functools import lru_cache

import numpy as np

from ..settings import SEMANTIC_MODEL_NAME

logger = logging.getLogger(__name__)
_embedding_lock = threading.RLock()
_sentence_embeddings: dict[str, np.ndarray] = {}
_reference_matrix_cache: dict[tuple[str, ...], np.ndarray] = {}


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(SEMANTIC_MODEL_NAME)


def invalidate_reference_embedding_cache() -> None:
    """Discard assembled reference matrices after the corpus changes.

    Individual sentence embeddings remain reusable: an unchanged reference
    sentence is never encoded a second time when a document is added, removed,
    archived, or restored.
    """
    with _embedding_lock:
        _reference_matrix_cache.clear()


def _normalized_embeddings(model, sentences: list[str]) -> np.ndarray:
    """Get normalized embeddings, encoding each previously unseen sentence once."""
    missing = []
    seen_missing: set[str] = set()
    for sentence in sentences:
        if sentence not in _sentence_embeddings and sentence not in seen_missing:
            missing.append(sentence)
            seen_missing.add(sentence)
    if missing:
        embeddings = model.encode(missing, convert_to_numpy=True, show_progress_bar=False)
        embeddings /= np.maximum(np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-12)
        _sentence_embeddings.update(zip(missing, embeddings))
    return np.vstack([_sentence_embeddings[sentence] for sentence in sentences])


def semantic_similarity_matrix(targets: list[str], references: list[str]) -> np.ndarray | None:
    """Return sentence-pair cosine scores, or ``None`` when SBERT is unavailable."""
    if not targets or not references:
        return None
    try:
        started = perf_counter()
        model = _model()
        # Upload sentences must always be encoded fresh; only reference
        # sentences are stable across requests and are safe to retain.
        target_embeddings = model.encode(targets, convert_to_numpy=True, show_progress_bar=False)
        target_embeddings /= np.maximum(np.linalg.norm(target_embeddings, axis=1, keepdims=True), 1e-12)
        reference_key = tuple(references)
        with _embedding_lock:
            reference_embeddings = _reference_matrix_cache.get(reference_key)
            if reference_embeddings is None:
                reference_embeddings = _normalized_embeddings(model, references)
                _reference_matrix_cache[reference_key] = reference_embeddings
        logger.info("Semantic similarity completed in %.3fs", perf_counter() - started)
        return np.clip(target_embeddings @ reference_embeddings.T, 0.0, 1.0)
    except Exception as exc:  # Model/dependency/network failures must not break legacy analysis.
        logger.warning("Semantic similarity unavailable; using lexical scoring only: %s", exc)
        return None
