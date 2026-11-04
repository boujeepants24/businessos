"""Embedders turn text into vectors so similar meanings land close together.

- `VoyageEmbedder`: real semantic embeddings from Voyage AI (Anthropic's recommended embeddings
  provider). Use this for any real knowledge base.
- `HashEmbedder`: deterministic feature hashing of words and word pairs. It needs no network or
  model download, which makes it right for tests and offline development, but it only matches
  shared words, not meaning. Hybrid retrieval still works with it because keyword search does the
  heavy lifting.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from .config import Settings

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    return (m / np.where(norms == 0, 1, norms)).astype(np.float32)


class HashEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def _vector(self, text: str) -> np.ndarray:
        words = _WORD.findall(text.lower())
        feats = words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]
        v = np.zeros(self.dim, dtype=np.float32)
        for f in feats:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            v[h % self.dim] += 1.0 if (h >> 63) == 0 else -1.0  # signed hashing reduces collisions' bias
        return v

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _normalize(np.stack([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalize(self._vector(text)[None, :])[0]


class VoyageEmbedder:
    """Voyage AI embeddings. Needs `pip install 'domain-rag[voyage]'` and VOYAGE_API_KEY."""

    _BATCH = 128

    def __init__(self, model: str = "voyage-3.5") -> None:
        try:
            import voyageai
        except ImportError as exc:
            raise RuntimeError("Voyage embeddings need: pip install 'domain-rag[voyage]'") from exc
        if not os.environ.get("VOYAGE_API_KEY"):
            raise RuntimeError("Set VOYAGE_API_KEY to use Voyage embeddings")
        self._client = voyageai.Client()
        self.model = model
        self.name = f"voyage:{model}"
        self.dim = 0  # learned from the first response

    def _embed(self, texts: Sequence[str], input_type: str) -> np.ndarray:
        rows: list[list[float]] = []
        for i in range(0, len(texts), self._BATCH):
            result = self._client.embed(list(texts[i : i + self._BATCH]), model=self.model, input_type=input_type)
            rows.extend([float(x) for x in e] for e in result.embeddings)
        m = _normalize(np.asarray(rows, dtype=np.float32))
        self.dim = m.shape[1] if m.size else self.dim
        return m

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "query")[0]


def make_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "voyage":
        return VoyageEmbedder(settings.voyage_model)
    return HashEmbedder()
