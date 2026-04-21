"""LLM-less relevance validator: alnum-normalized substring match.

Filters EvidenceItems whose title or text (normalized to lowercase alphanumerics
only, stripping spaces/hyphens/punctuation) contains the normalized product name.
"""

from __future__ import annotations

from ari_core import EvidenceItem


def _normalize(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


def is_relevant(item: EvidenceItem, product_name: str) -> bool:
    needle = _normalize(product_name)
    if not needle:
        return True
    haystack = _normalize((item.title or "") + " " + (item.text or ""))
    return needle in haystack


def filter_items(items: list[EvidenceItem], product_name: str) -> list[EvidenceItem]:
    return [it for it in items if is_relevant(it, product_name)]
