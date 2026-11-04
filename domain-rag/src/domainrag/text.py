"""Small text utilities shared by keyword search and relevance filtering."""

from __future__ import annotations

import re

_WORD = re.compile(r"\w+", re.UNICODE)

# Words too common to say anything about relevance. Kept short on purpose: domain words stay.
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "about",
        "after",
        "again",
        "all",
        "also",
        "am",
        "any",
        "because",
        "before",
        "being",
        "both",
        "down",
        "each",
        "few",
        "further",
        "here",
        "just",
        "more",
        "most",
        "no",
        "nor",
        "not",
        "now",
        "only",
        "other",
        "out",
        "over",
        "own",
        "same",
        "she",
        "he",
        "her",
        "his",
        "him",
        "some",
        "such",
        "too",
        "under",
        "until",
        "up",
        "very",
        "off",
        "once",
        "while",
    ]
)


def stem(word: str) -> str:
    """A deliberately light stemmer: enough to match 'returns'/'return', 'services'/'service'."""
    for suffix in ("ing", "ies", "ied", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            return base + "y" if suffix in ("ies", "ied") else base
    return word


def content_terms(text: str) -> list[str]:
    """Lower-cased words minus stopwords and 1-letter tokens, in order, de-duplicated."""
    words = [w for w in _WORD.findall(text.lower()) if len(w) > 1 and w not in STOPWORDS]
    return list(dict.fromkeys(words))


def coverage(query: str, passage: str) -> float:
    """Share of the query's meaningful words (stemmed) that appear in the passage."""
    q = {stem(w) for w in content_terms(query)}
    if not q:
        return 0.0
    p = {stem(w) for w in _WORD.findall(passage.lower())}
    return len(q & p) / len(q)
