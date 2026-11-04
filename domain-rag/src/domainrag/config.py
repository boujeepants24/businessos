"""Settings, read from environment variables so nothing secret lives in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = (".md", ".markdown", ".txt", ".html", ".htm", ".pdf")


@dataclass(frozen=True)
class Settings:
    docs_dir: Path
    """Folder of source documents. The only place ingestion reads from."""

    db_path: Path
    """SQLite file holding chunks, embeddings and the keyword index."""

    domain: str = "the documents in this knowledge base"
    """Plain-language description of the subject, used in the answer prompt."""

    embedder: str = "hash"
    """'voyage' for real semantic embeddings, 'hash' for an offline, non-semantic fallback."""

    voyage_model: str = "voyage-3.5"
    claude_model: str = "claude-opus-5-5"
    effort: str = "medium"

    chunk_size: int = 1200
    """Target chunk length in characters (roughly 250-300 tokens of English)."""

    chunk_overlap: int = 200
    top_k: int = 6
    max_file_mb: int = 20

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            docs_dir=Path(env.get("DOMAINRAG_DOCS_DIR", "knowledge")).resolve(),
            db_path=Path(env.get("DOMAINRAG_DB", ".domainrag/index.db")).resolve(),
            domain=env.get("DOMAINRAG_DOMAIN", cls.domain),
            embedder=env.get("DOMAINRAG_EMBEDDER", cls.embedder),
            voyage_model=env.get("DOMAINRAG_VOYAGE_MODEL", cls.voyage_model),
            claude_model=env.get("DOMAINRAG_MODEL", cls.claude_model),
            effort=env.get("DOMAINRAG_EFFORT", cls.effort),
            chunk_size=int(env.get("DOMAINRAG_CHUNK_SIZE", cls.chunk_size)),
            chunk_overlap=int(env.get("DOMAINRAG_CHUNK_OVERLAP", cls.chunk_overlap)),
            top_k=int(env.get("DOMAINRAG_TOP_K", cls.top_k)),
        )

    def validate(self) -> None:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("DOMAINRAG_CHUNK_OVERLAP must be smaller than DOMAINRAG_CHUNK_SIZE")
        if not 1 <= self.top_k <= 50:
            raise ValueError("DOMAINRAG_TOP_K must be between 1 and 50")
        if self.embedder not in ("hash", "voyage"):
            raise ValueError("DOMAINRAG_EMBEDDER must be 'hash' or 'voyage'")
        if self.effort not in ("low", "medium", "high", "xhigh", "max"):
            raise ValueError("DOMAINRAG_EFFORT must be low, medium, high, xhigh or max")
