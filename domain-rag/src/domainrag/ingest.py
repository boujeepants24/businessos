"""Incremental ingestion: only changed files are re-embedded, removed files are dropped."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from .chunking import chunk_document
from .config import Settings
from .embeddings import Embedder
from .loaders import discover, load_document
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    chunks_written: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"{len(self.added)} added, {len(self.updated)} updated, {len(self.unchanged)} unchanged, "
            f"{len(self.removed)} removed, {len(self.failed)} failed, {self.chunks_written} chunks written"
        )


def ingest(settings: Settings, store: Store, embedder: Embedder, rebuild: bool = False) -> IngestReport:
    if rebuild:
        store.reset()
    store.bind_embedder(embedder.name)
    report = IngestReport()
    root = settings.docs_dir
    seen: set[str] = set()

    for path in discover(root):
        rel = path.relative_to(root).as_posix()
        seen.add(rel)
        try:
            doc = load_document(root, path, settings.max_file_mb)
            previous = store.document_hash(doc.source)
            if previous == doc.sha256:
                report.unchanged.append(doc.source)
                continue
            chunks = chunk_document(doc, settings.chunk_size, settings.chunk_overlap)
            if not chunks:
                report.failed[doc.source] = "no text could be extracted"
                continue
            vectors = embedder.embed_documents([c.embedding_text() for c in chunks])
            store.upsert_document(doc, chunks, vectors)
            (report.updated if previous else report.added).append(doc.source)
            report.chunks_written += len(chunks)
        except Exception as exc:  # one bad file must not stop the rest
            log.warning("Skipping %s: %s", rel, exc)
            report.failed[rel] = str(exc)

    for entry in store.list_documents():
        source = str(entry["source"])
        if source not in seen:
            store.delete_document(source)
            report.removed.append(source)
    return report
