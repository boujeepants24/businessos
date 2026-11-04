"""SQLite storage: documents, chunks, embedding vectors and a full-text (BM25) keyword index.

One file, no server. Vector search is exact (brute-force cosine over a numpy matrix), which is
fast and simple up to roughly 100k chunks; past that, swap in pgvector or a vector database
behind the same `vector_search` method.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .chunking import Chunk
from .loaders import Document
from .text import content_terms

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
    source TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    n_chunks INTEGER NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    rowid INTEGER PRIMARY KEY,
    id TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL REFERENCES documents(source) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    heading TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, heading, title, content='chunks', content_rowid='rowid', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, heading, title) VALUES (new.rowid, new.text, new.heading, new.title);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, heading, title) VALUES ('delete', old.rowid, old.text, old.heading, old.title);
END;
"""


@dataclass(frozen=True)
class StoredChunk:
    id: str
    source: str
    title: str
    heading: str
    index: int
    text: str


class EmbedderMismatch(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._matrix: np.ndarray | None = None
        self._matrix_ids: list[str] = []

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------ metadata

    def get_meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def bind_embedder(self, name: str) -> None:
        """An index is only valid for the embedder that built it. Refuse to mix them."""
        current = self.get_meta("embedder")
        if current is None:
            with self._db:
                self._db.execute("INSERT INTO meta(key, value) VALUES ('embedder', ?)", (name,))
        elif current != name:
            raise EmbedderMismatch(
                f"This index was built with '{current}' but the current embedder is '{name}'. "
                "Run `domainrag ingest --rebuild` to re-embed everything."
            )

    def reset(self) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM chunks")
            self._db.execute("DELETE FROM documents")
            self._db.execute("DELETE FROM meta")
        self._matrix = None

    # ------------------------------------------------------------------ writes

    def document_hash(self, source: str) -> str | None:
        row = self._db.execute("SELECT sha256 FROM documents WHERE source = ?", (source,)).fetchone()
        return row["sha256"] if row else None

    def upsert_document(self, doc: Document, chunks: Sequence[Chunk], vectors: np.ndarray) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk is required")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock, self._db:  # one transaction: a crash never leaves half a document
            self._db.execute("DELETE FROM chunks WHERE source = ?", (doc.source,))
            self._db.execute(
                "INSERT INTO documents(source, title, sha256, n_chunks, ingested_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET title=excluded.title, sha256=excluded.sha256, "
                "n_chunks=excluded.n_chunks, ingested_at=excluded.ingested_at",
                (doc.source, doc.title, doc.sha256, len(chunks), now),
            )
            self._db.executemany(
                "INSERT INTO chunks(id, source, idx, title, heading, text, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (c.id, c.source, c.index, c.title, c.heading, c.text, np.asarray(v, dtype=np.float32).tobytes())
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
        self._matrix = None

    def delete_document(self, source: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM chunks WHERE source = ?", (source,))
            self._db.execute("DELETE FROM documents WHERE source = ?", (source,))
        self._matrix = None

    # ------------------------------------------------------------------ reads

    def list_documents(self) -> list[dict[str, object]]:
        rows = self._db.execute("SELECT source, title, n_chunks, ingested_at FROM documents ORDER BY source").fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict[str, int]:
        docs = self._db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"documents": docs, "chunks": chunks}

    def get_chunk(self, chunk_id: str) -> StoredChunk | None:
        row = self._db.execute(
            "SELECT id, source, title, heading, idx, text FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return self._row(row) if row else None

    def get_chunks(self, ids: Sequence[str]) -> dict[str, StoredChunk]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self._db.execute(
            f"SELECT id, source, title, heading, idx, text FROM chunks WHERE id IN ({marks})", list(ids)
        ).fetchall()
        return {r["id"]: self._row(r) for r in rows}

    @staticmethod
    def _row(r: sqlite3.Row) -> StoredChunk:
        return StoredChunk(
            id=r["id"], source=r["source"], title=r["title"], heading=r["heading"], index=r["idx"], text=r["text"]
        )

    # ------------------------------------------------------------------ search

    @staticmethod
    def fts_query(text: str) -> str | None:
        """User text → a safe FTS5 query: every word quoted (so operators like NOT/NEAR or stray
        quotes can't change the query), OR-ed together so partial matches still rank."""
        terms = content_terms(text)[:32]
        return " OR ".join(f'"{t}"' for t in terms) or None

    def keyword_search(self, query: str, k: int, sources: Sequence[str] | None = None) -> list[tuple[str, float]]:
        match = self.fts_query(query)
        if not match:
            return []
        sql = (
            "SELECT c.id, bm25(chunks_fts, 1.0, 0.5, 0.3) AS score FROM chunks_fts "
            "JOIN chunks c ON c.rowid = chunks_fts.rowid WHERE chunks_fts MATCH ?"
        )
        params: list[object] = [match]
        if sources:
            sql += f" AND c.source IN ({','.join('?' * len(sources))})"
            params.extend(sources)
        sql += " ORDER BY score LIMIT ?"
        params.append(k)
        # bm25() is lower-is-better; flip the sign so higher means more relevant everywhere.
        return [(r["id"], -float(r["score"])) for r in self._db.execute(sql, params).fetchall()]

    def _load_matrix(self) -> None:
        rows = self._db.execute("SELECT id, embedding FROM chunks ORDER BY rowid").fetchall()
        self._matrix_ids = [r["id"] for r in rows]
        self._matrix = (
            np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
            if rows
            else np.zeros((0, 0), dtype=np.float32)
        )

    def vector_search(
        self, query_vec: np.ndarray, k: int, sources: Sequence[str] | None = None
    ) -> list[tuple[str, float]]:
        with self._lock:
            if self._matrix is None:
                self._load_matrix()
            matrix, ids = self._matrix, self._matrix_ids
        assert matrix is not None
        if matrix.size == 0:
            return []
        scores = matrix @ np.asarray(query_vec, dtype=np.float32)  # vectors are unit length: dot = cosine
        order = np.argsort(-scores)
        allowed = set(sources) if sources else None
        out: list[tuple[str, float]] = []
        if allowed is not None:
            by_id = self.get_chunks([ids[i] for i in order[: max(k * 20, 200)]])
        for i in order:
            cid = ids[i]
            if allowed is not None and (cid not in by_id or by_id[cid].source not in allowed):
                continue
            out.append((cid, float(scores[i])))
            if len(out) == k:
                break
        return out

    def export_json(self) -> str:
        """A small, human-readable summary for debugging."""
        return json.dumps(
            {"embedder": self.get_meta("embedder"), **self.counts(), "documents": self.list_documents()}, indent=2
        )
