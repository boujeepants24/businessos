"""Turn files in the knowledge folder into plain-text documents."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from .config import SUPPORTED_SUFFIXES

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    source: str  # path relative to the knowledge folder, with forward slashes
    title: str
    text: str
    sha256: str


class _TextExtractor(HTMLParser):
    """Keeps visible text and headings; drops scripts, styles and markup."""

    _SKIP = {"script", "style", "noscript", "template", "svg"}
    _BLOCK = {"p", "div", "li", "br", "tr", "section", "article", "table", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False
        self._heading: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif re.fullmatch(r"h[1-6]", tag):
            self._heading = int(tag[1])
            self.parts.append("\n\n" + "#" * self._heading + " ")
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif re.fullmatch(r"h[1-6]", tag):
            self._heading = None
            self.parts.append("\n\n")
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data.strip()
            return
        self.parts.append(data)


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # optional dependency
        raise RuntimeError("PDF support needs pypdf: pip install 'domain-rag[pdf]'") from exc
    reader = PdfReader(str(path))
    pages = [f"[page {i}]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, start=1)]
    return "\n\n".join(pages)


def safe_resolve(root: Path, path: Path) -> Path:
    """Resolve `path` and refuse anything outside `root` (symlinks and ../ included)."""
    root = root.resolve()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise PermissionError(f"{path} is outside the knowledge folder")
    return resolved


def load_document(root: Path, path: Path, max_file_mb: int = 20) -> Document:
    resolved = safe_resolve(root, path)
    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {suffix}")
    raw = resolved.read_bytes()
    if len(raw) > max_file_mb * 1024 * 1024:
        raise ValueError(f"{path.name} is larger than {max_file_mb} MB")

    title = ""
    if suffix == ".pdf":
        text = _read_pdf(resolved)
    else:
        decoded = raw.decode("utf-8", errors="replace")
        if suffix in (".html", ".htm"):
            parser = _TextExtractor()
            parser.feed(decoded)
            text, title = "".join(parser.parts), parser.title
        else:
            text = decoded

    text = _clean(text)
    if not title:
        heading = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        title = heading.group(1).strip() if heading else resolved.stem.replace("-", " ").replace("_", " ")

    return Document(
        source=resolved.relative_to(root.resolve()).as_posix(),
        title=title[:200],
        text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def discover(root: Path) -> list[Path]:
    """All supported files under `root`, skipping hidden files and folders."""
    if not root.exists():
        return []
    found = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            found.append(path)
    return found
