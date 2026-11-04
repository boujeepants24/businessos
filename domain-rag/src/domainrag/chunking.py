"""Split documents into overlapping, heading-aware chunks.

Chunks follow the document's own structure: text is first split at markdown headings, so a chunk
never mixes two sections, then paragraphs are packed up to `chunk_size` characters. Each chunk
remembers its heading path ("Setup > Wiring"), which is prepended when embedding so a short
paragraph still carries the context of where it sits.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .loaders import Document

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    title: str
    heading: str
    index: int
    text: str

    def embedding_text(self) -> str:
        context = section_label(self.title, self.heading)
        return f"{context}\n\n{self.text}" if context else self.text


def section_label(title: str, heading: str) -> str:
    """'Guide > Error codes > F28', without repeating the title when the top heading is the title."""
    if not heading:
        return title
    if heading == title or heading.startswith(f"{title} > "):
        return heading
    return f"{title} > {heading}" if title else heading


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading path, body) pairs in document order."""
    sections: list[tuple[str, str]] = []
    path: list[tuple[int, str]] = []
    last_end, last_heading = 0, ""
    for match in _HEADING.finditer(text):
        body = text[last_end : match.start()].strip()
        if body:
            sections.append((last_heading, body))
        level, name = len(match.group(1)), match.group(2).strip()
        path = [(lvl, n) for lvl, n in path if lvl < level] + [(level, name)]
        last_heading = " > ".join(n for _, n in path)
        last_end = match.end()
    tail = text[last_end:].strip()
    if tail:
        sections.append((last_heading, tail))
    return sections


def _pieces(body: str, size: int) -> list[str]:
    """Paragraphs, with any paragraph longer than `size` split at sentence ends, then hard-cut."""
    out: list[str] = []
    for para in (p.strip() for p in body.split("\n\n")):
        if not para:
            continue
        if len(para) <= size:
            out.append(para)
            continue
        buf = ""
        for sentence in _SENTENCE_END.split(para):
            while len(sentence) > size:  # a single run-on "sentence" (tables, code): hard cut
                out.append(sentence[:size])
                sentence = sentence[size:]
            if buf and len(buf) + 1 + len(sentence) > size:
                out.append(buf)
                buf = sentence
            else:
                buf = f"{buf} {sentence}".strip()
        if buf:
            out.append(buf)
    return out


def _tail(text: str, overlap: int) -> str:
    """The last `overlap` characters, starting at a word boundary."""
    if overlap <= 0 or len(text) <= overlap:
        return text if overlap > 0 else ""
    cut = text[-overlap:]
    space = cut.find(" ")
    return cut[space + 1 :] if 0 <= space < len(cut) - 1 else cut


def chunk_document(doc: Document, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[Chunk]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    chunks: list[Chunk] = []

    def emit(heading: str, text: str) -> None:
        index = len(chunks)
        digest = hashlib.sha256(f"{doc.source}\x00{index}\x00{text}".encode()).hexdigest()[:16]
        chunks.append(Chunk(id=digest, source=doc.source, title=doc.title, heading=heading, index=index, text=text))

    for heading, body in _sections(doc.text):
        buf = ""
        # Pieces leave room for the carried-over overlap plus the "\n\n" joiner, so no chunk
        # ever exceeds chunk_size.
        for piece in _pieces(body, chunk_size - chunk_overlap - 2):
            if buf and len(buf) + 2 + len(piece) > chunk_size:
                emit(heading, buf)
                buf = _tail(buf, chunk_overlap)
            buf = f"{buf}\n\n{piece}" if buf else piece
        if buf.strip():
            emit(heading, buf)
    return chunks
