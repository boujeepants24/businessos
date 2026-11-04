from __future__ import annotations

import numpy as np
import pytest

from domainrag.embeddings import HashEmbedder
from domainrag.ingest import ingest
from domainrag.store import EmbedderMismatch, Store


def test_ingest_indexes_every_document(index):
    assert index.store.counts()["documents"] == 4
    assert {d["source"] for d in index.store.list_documents()} == {
        "heating-guide.md",
        "warranty.txt",
        "faq.html",
        "injected.md",
    }


def test_reingest_skips_unchanged_updates_changed_and_drops_removed(index):
    report = ingest(index.settings, index.store, index.embedder)
    assert sorted(report.unchanged) == sorted(d["source"] for d in index.store.list_documents())
    assert report.chunks_written == 0

    (index.settings.docs_dir / "warranty.txt").write_text("Northfield C30 Warranty Terms\n\nNow a 10 year warranty.")
    (index.settings.docs_dir / "faq.html").unlink()
    report = ingest(index.settings, index.store, index.embedder)
    assert report.updated == ["warranty.txt"]
    assert report.removed == ["faq.html"]
    hits = index.retriever.search("how many years warranty", k=3)
    assert "10 year" in hits[0].chunk.text
    assert all("7 year" not in h.chunk.text for h in hits), "old chunks of an updated file are gone"


def test_exact_codes_are_found_by_keyword_search(index):
    hits = index.retriever.search("F28", k=3)
    assert hits[0].chunk.heading.endswith("F28 ignition failure")
    assert hits[0].keyword_rank == 1


def test_hybrid_ranks_the_right_section_first(index):
    cases = {
        "my radiator is cold at the top": "faq.html",
        "what pressure should the gauge show": "heating-guide.md",
        "how long is the warranty": "warranty.txt",
        "what does the annual service include": "heating-guide.md",
    }
    for query, expected in cases.items():
        assert index.retriever.search(query, k=3)[0].chunk.source == expected, query


def test_unrelated_question_returns_nothing(index):
    # "return" shares a stem with "If F28 returns" in the corpus: one weak word must not count as relevance.
    assert index.retriever.search("quarterly tax return deadlines", k=5) == []
    assert index.retriever.search("what is the capital of France", k=5) == []
    assert index.retriever.search("   ", k=5) == []


def test_source_filter(index):
    hits = index.retriever.search("warranty service engineer", k=5, sources=["heating-guide.md"])
    assert hits and all(h.chunk.source == "heating-guide.md" for h in hits)


@pytest.mark.parametrize("hostile", ['" OR 1=1 --', "NEAR(a b)", "text:secret*", "'); DROP TABLE chunks; --", "^^^"])
def test_hostile_queries_are_safe(index, hostile):
    index.retriever.search(hostile, k=3)  # must not raise
    assert index.store.counts()["chunks"] > 0


def test_index_refuses_a_different_embedder(index):
    with pytest.raises(EmbedderMismatch):
        index.store.bind_embedder("voyage:voyage-3.5")


def test_rebuild_resets_the_embedder_binding(index):
    ingest(index.settings, index.store, HashEmbedder(dim=256), rebuild=True)
    assert index.store.get_meta("embedder") == "hash-256"


def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder(dim=64)
    a, b = e.embed_documents(["boiler pressure", "boiler pressure"])
    assert np.allclose(a, b)
    assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-5
    assert e.embed_documents([]).shape == (0, 64)


def test_store_writes_are_atomic(tmp_path):
    store = Store(tmp_path / "x.db")
    from domainrag.chunking import Chunk
    from domainrag.loaders import Document

    doc = Document("a.md", "A", "text", "1" * 64)
    chunks = [Chunk("0123456789abcdef", "a.md", "A", "", 0, "text")]
    with pytest.raises(ValueError):
        store.upsert_document(doc, chunks, np.zeros((2, 4), dtype=np.float32))
    assert store.counts() == {"documents": 0, "chunks": 0}
