"""Chunk + embed artifacts into a single vector store partitioned by artifact_id.

Production path: a FAISS index (inner-product on normalized vectors == cosine)
with a parallel metadata list; each chunk carries its ``artifact_id`` so an
artifact is an independently retrievable namespace (filter by artifact_id, then
search). When faiss is unavailable we use a pure-Python brute-force cosine
search over the same in-memory records -- identical API, no numpy needed.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..config import settings
from .embeddings import Embedder, get_embedder
from .registry import ARTIFACTS, ArtifactMeta

log = logging.getLogger(__name__)


@dataclass
class Chunk:
    artifact_id: str
    text: str
    source_file: str
    chunk_index: int


@dataclass
class RetrievedChunk:
    artifact_id: str
    text: str
    source_file: str
    score: float


def chunk_markdown(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    """Split markdown into overlapping chunks, preferring section boundaries."""
    # Split on markdown headings first so chunks stay topically coherent.
    sections = re.split(r"(?m)^(?=#{1,6}\s)", text)
    chunks: List[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_chars:
            chunks.append(section)
            continue
        start = 0
        while start < len(section):
            end = min(start + max_chars, len(section))
            chunks.append(section[start:end].strip())
            if end == len(section):
                break
            start = end - overlap
    return [c for c in chunks if c]


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class ArtifactStore:
    """Builds/persists/queries the partitioned artifact vector store."""

    def __init__(self, embedder: Optional[Embedder] = None):
        self.embedder = embedder or get_embedder()
        self._chunks: List[Chunk] = []
        self._vectors: List[List[float]] = []
        self._faiss = None  # faiss index if available
        self._built = False

    # -- ingestion --------------------------------------------------------
    @staticmethod
    def _read_artifact_files(meta: ArtifactMeta) -> List[tuple[str, str]]:
        """Return (filename, text) for each markdown file of an artifact.

        Two shapes, because the two wings genuinely have two shapes and
        normalising them on disk would mean copying the benchmark's 706 KB of
        grounding into a second location that then drifts:

          directory   the edge artifacts, ``grounding/<id>/*.md`` (README +
                      notebook markdown, several files per artifact)
          single file  the chameleon corpus, one ``grounding/A*.md`` per
                      artifact, read in place from ``settings.corpus_dir``

        A file wins when ``grounding_file`` is set; otherwise the directory is
        tried, exactly as before.
        """
        out: List[tuple[str, str]] = []
        single = getattr(meta, "grounding_file", None)
        if single is not None:
            path = Path(single)
            if path.is_file():
                try:
                    return [(path.name, path.read_text(encoding="utf-8"))]
                except OSError as exc:
                    # Not silent: an artifact that loses its grounding drops out
                    # of retrieval entirely, and that must be visible.
                    log.warning("cannot read grounding for %s (%s)",
                                meta.artifact_id, exc)
                    return out
            log.warning("grounding file for %s does not exist: %s",
                        meta.artifact_id, path)
            return out

        adir = meta.dir()
        if not adir.is_dir():
            return out
        for path in sorted(adir.glob("*.md")):
            try:
                out.append((path.name, path.read_text(encoding="utf-8")))
            except OSError as exc:
                log.warning("cannot read %s for %s (%s)",
                            path.name, meta.artifact_id, exc)
                continue
        return out

    def build(self, artifacts: Optional[List[ArtifactMeta]] = None) -> "ArtifactStore":
        artifacts = artifacts or ARTIFACTS
        self._chunks = []
        for meta in artifacts:
            for fname, text in self._read_artifact_files(meta):
                for i, ctext in enumerate(chunk_markdown(text)):
                    self._chunks.append(
                        Chunk(meta.artifact_id, ctext, fname, i)
                    )
        if not self._chunks:
            raise RuntimeError(
                f"No artifact text found under {settings.grounding_dir} "
                f"or {settings.corpus_dir}. Check GROUNDING_DIR / "
                "CHAMELEON_CORPUS_DIR and that the grounding files exist."
            )
        self._vectors = self.embedder.embed([c.text for c in self._chunks])
        self._build_faiss()
        self._built = True
        return self

    def _build_faiss(self) -> None:
        if settings.offline:
            return
        try:
            import faiss  # noqa: F401
            import numpy as np
        except Exception:  # noqa: BLE001
            self._faiss = None
            return
        mat = np.array(self._vectors, dtype="float32")
        index = faiss.IndexFlatIP(mat.shape[1])
        index.add(mat)
        self._faiss = index
        self._np = np

    # -- persistence ------------------------------------------------------
    def save(self, path: Optional[Path] = None) -> Path:
        path = Path(path or settings.data_dir / "artifact_store.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "embedder": self.embedder.name,
            "dim": self.embedder.dim,
            "chunks": [asdict(c) for c in self._chunks],
            "vectors": self._vectors,
        }
        path.write_text(json.dumps(payload))
        return path

    def load(self, path: Optional[Path] = None) -> "ArtifactStore":
        path = Path(path or settings.data_dir / "artifact_store.json")
        payload = json.loads(path.read_text())
        self._chunks = [Chunk(**c) for c in payload["chunks"]]
        self._vectors = payload["vectors"]
        self._build_faiss()
        self._built = True
        return self

    # -- retrieval --------------------------------------------------------
    def search(
        self,
        query: str,
        artifact_ids: Optional[List[str]] = None,
        k: int = 4,
    ) -> List[RetrievedChunk]:
        """Top-k chunks for ``query``, restricted to ``artifact_ids`` if given."""
        if not self._built:
            raise RuntimeError("ArtifactStore.search called before build()/load().")
        qvec = self.embedder.embed([query])[0]
        allowed = set(artifact_ids) if artifact_ids else None

        scored: List[RetrievedChunk] = []
        for chunk, vec in zip(self._chunks, self._vectors):
            if allowed is not None and chunk.artifact_id not in allowed:
                continue
            scored.append(
                RetrievedChunk(
                    artifact_id=chunk.artifact_id,
                    text=chunk.text,
                    source_file=chunk.source_file,
                    score=_dot(qvec, vec),
                )
            )
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    def artifact_ids(self) -> List[str]:
        seen: List[str] = []
        for c in self._chunks:
            if c.artifact_id not in seen:
                seen.append(c.artifact_id)
        return seen

    @property
    def num_chunks(self) -> int:
        return len(self._chunks)
