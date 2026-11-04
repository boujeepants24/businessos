from __future__ import annotations

from pathlib import Path

import pytest

from domainrag.chunking import chunk_document
from domainrag.loaders import Document, discover, load_document

from .conftest import CORPUS


def test_markdown_title_and_hash():
    doc = load_document(CORPUS, CORPUS / "heating-guide.md")
    assert doc.source == "heating-guide.md"
    assert doc.title == "Northfield Combi Boiler Guide"
    assert len(doc.sha256) == 64


def test_html_keeps_visible_text_and_drops_scripts():
    doc = load_document(CORPUS, CORPUS / "faq.html")
    assert doc.title == "Northfield FAQ"
    assert "## Radiators" in doc.text and "Bleed it with a radiator key" in doc.text
    assert "tracking" not in doc.text and "color:red" not in doc.text


def test_plain_text_title_falls_back_to_filename():
    assert load_document(CORPUS, CORPUS / "warranty.txt").title == "warranty"


def test_refuses_paths_outside_the_knowledge_folder(tmp_path: Path):
    outside = tmp_path / "secret.md"
    outside.write_text("# secret")
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "link.md").symlink_to(outside)
    with pytest.raises(PermissionError):
        load_document(root, root / "link.md")
    with pytest.raises(PermissionError):
        load_document(root, root / ".." / "secret.md")


def test_discover_skips_hidden_and_unsupported(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "notes.md").write_text("x")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "ok.md").write_text("# ok")
    assert [p.name for p in discover(tmp_path)] == ["ok.md"]


def _doc(text: str) -> Document:
    return Document(source="t.md", title="T", text=text, sha256="0" * 64)


def test_chunks_follow_headings_and_respect_size():
    doc = load_document(CORPUS, CORPUS / "heating-guide.md")
    chunks = chunk_document(doc, chunk_size=300, chunk_overlap=60)
    assert all(len(c.text) <= 300 for c in chunks)
    f28 = [c for c in chunks if "F28 means" in c.text]
    assert f28 and f28[0].heading == "Northfield Combi Boiler Guide > Error codes > F28 ignition failure"
    assert not any("F28 means" in c.text and "F22 means" in c.text for c in chunks), "sections never mix"
    assert f28[0].embedding_text().startswith("Northfield Combi Boiler Guide > Error codes > F28 ignition failure\n")


def test_long_text_is_split_with_overlap():
    sentences = " ".join(f"Sentence number {i} talks about pressure." for i in range(80))
    chunks = chunk_document(_doc(sentences), chunk_size=400, chunk_overlap=100)
    assert len(chunks) > 3
    assert all(len(c.text) <= 400 for c in chunks)
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert a.text[-40:].split()[-1] in b.text, "consecutive chunks share overlapping text"


def test_run_on_text_without_sentences_is_hard_cut():
    chunks = chunk_document(_doc("x" * 2500), chunk_size=500, chunk_overlap=50)
    assert all(len(c.text) <= 500 for c in chunks)
    assert sum(c.text.count("x") for c in chunks) >= 2500


def test_chunk_ids_are_stable_and_unique():
    doc = load_document(CORPUS, CORPUS / "heating-guide.md")
    a = chunk_document(doc, 300, 60)
    b = chunk_document(doc, 300, 60)
    assert [c.id for c in a] == [c.id for c in b]
    assert len({c.id for c in a}) == len(a)


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_document(_doc("hello"), chunk_size=100, chunk_overlap=100)
