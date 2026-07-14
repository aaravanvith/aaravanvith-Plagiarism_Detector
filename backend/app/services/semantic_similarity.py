"""Optional SBERT semantic-similarity adapter.

The model is loaded only when semantic scoring is enabled and first needed.
If it cannot be loaded, callers receive ``None`` and can retain the legacy
TF-IDF workflow rather than failing an upload.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from ..settings import SEMANTIC_MODEL_NAME

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(SEMANTIC_MODEL_NAME)


def semantic_similarity_matrix(targets: list[str], references: list[str]) -> np.ndarray | None:
    """Return sentence-pair cosine scores, or ``None`` when SBERT is unavailable."""
    if not targets or not references:
        return None
    try:
        model = _model()
        target_embeddings = model.encode(targets, convert_to_numpy=True, show_progress_bar=False)
        reference_embeddings = model.encode(references, convert_to_numpy=True, show_progress_bar=False)
        target_embeddings /= np.maximum(np.linalg.norm(target_embeddings, axis=1, keepdims=True), 1e-12)
        reference_embeddings /= np.maximum(np.linalg.norm(reference_embeddings, axis=1, keepdims=True), 1e-12)
        return np.clip(target_embeddings @ reference_embeddings.T, 0.0, 1.0)
    except Exception as exc:  # Model/dependency/network failures must not break legacy analysis.
        logger.warning("Semantic similarity unavailable; using lexical scoring only: %s", exc)
        return None
