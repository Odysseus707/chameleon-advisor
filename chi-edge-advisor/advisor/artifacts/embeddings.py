"""Embedding backends.

Production path mirrors RAG-docs-chameleon: BAAI/bge-large-en-v1.5 via
sentence-transformers. When that stack (or credentials/model weights) is
unavailable -- or ADVISOR_OFFLINE is set -- we fall back to a deterministic,
dependency-free hashing embedder so retrieval, the router, and tests all run
offline. Both return plain ``List[List[float]]`` so no numpy is required.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import List, Protocol

from ..config import settings

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


class Embedder(Protocol):
    dim: int
    name: str

    def embed(self, texts: List[str]) -> List[List[float]]: ...


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashingEmbedder:
    """Deterministic hashing bag-of-words embedder (offline fallback).

    Feature-hashes tokens into a fixed-width vector with signed buckets, then
    L2-normalizes. Cosine similarity on these vectors approximates lexical
    overlap -- weaker than bge, but stable, fast, and dependency-free.
    """

    name = "hashing-fallback"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = hashlib.md5(tok.encode()).digest()
            bucket = int.from_bytes(h[:4], "big") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[bucket] += sign
        return _l2_normalize(vec)

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]


class BgeEmbedder:
    """BAAI/bge-large-en-v1.5 via sentence-transformers (production path)."""

    name = "bge-large-en-v1.5"

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name or settings.embedding_model)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> List[List[float]]:
        # normalize_embeddings=True => cosine == dot product (matches FAISS IP).
        vecs = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return [list(map(float, v)) for v in vecs]


def get_embedder() -> Embedder:
    """Pick bge when available (and not forced offline); else hashing."""
    if settings.offline:
        return HashingEmbedder()
    try:
        return BgeEmbedder()
    except Exception:  # noqa: BLE001 - no torch/weights/network -> fallback
        return HashingEmbedder()
