"""Company deduplication (§51)."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

_LEGAL_SUFFIXES = re.compile(
    r"\b(inc|inc\.|llc|l\.l\.c|ltd|ltd\.|limited|corp|corporation|co|co\.|"
    r"gmbh|bv|b\.v|nv|sas|sarl|pty|plc|ab|oy|as|aps|srl|spa|pvt|private)\b",
    re.I)
_NOISE = re.compile(r"[^a-z0-9 ]+")


def canonical_name(name: str | None) -> str:
    if not name:
        return ""
    value = name.lower()
    value = re.sub(r"\|.*$|—.*$|-\s+(shop|store|official).*$", "", value)
    value = _LEGAL_SUFFIXES.sub(" ", value)
    value = _NOISE.sub(" ", value)
    return " ".join(value.split())


def name_similarity(a: str | None, b: str | None) -> float:
    ca, cb = canonical_name(a), canonical_name(b)
    if not ca or not cb:
        return 0.0
    return fuzz.token_sort_ratio(ca, cb) / 100.0


def is_duplicate(name_a: str | None, domain_a: str | None,
                 name_b: str | None, domain_b: str | None,
                 threshold: float = 0.92) -> bool:
    """Domain equality is authoritative; name similarity is a secondary check."""
    if domain_a and domain_b and domain_a.lower() == domain_b.lower():
        return True
    return name_similarity(name_a, name_b) >= threshold
