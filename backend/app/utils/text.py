"""Text cleaning, snippet extraction and hashing."""
from __future__ import annotations

import hashlib
import re

WHITESPACE = re.compile(r"\s+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE.sub(" ", value).strip()


def content_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8", "ignore")).hexdigest()


def snippet_around(text: str, needle: str, radius: int = 160) -> str | None:
    """Return the sentence(s) containing `needle` - this becomes the stored
    evidence string, so it must be verbatim from the source (§29)."""
    if not text or not needle:
        return None
    low = text.lower()
    idx = low.find(needle.lower())
    if idx == -1:
        return None
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    fragment = clean_text(text[start:end])
    if start > 0:
        fragment = "..." + fragment
    if end < len(text):
        fragment = fragment + "..."
    return fragment


def best_sentence(text: str, needle: str, max_len: int = 300) -> str | None:
    """Prefer a clean whole sentence over a raw character window."""
    if not text or not needle:
        return None
    for sentence in _SENTENCE_SPLIT.split(clean_text(text)):
        if needle.lower() in sentence.lower():
            return sentence.strip()[:max_len]
    return snippet_around(text, needle)


def contains_phrase(text: str, phrase: str) -> bool:
    """Word-boundary-aware substring match; avoids 'cart' matching 'cartoon'."""
    if not text or not phrase:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def truncate(value: str | None, limit: int) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else value[:limit].rsplit(" ", 1)[0] + "..."
