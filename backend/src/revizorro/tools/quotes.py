"""Deterministic check that every quoted fragment really exists in the document."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from revizorro.domain.models import Document

_QUOTES = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "'": '"', "`": "", "ё": "е"})
_DASHES = re.compile(r"[‐-―−]")
_SPACES = re.compile(r"[\s  ]+")
_MARKUP = re.compile(r"[*_#>]")
_EDGE = re.compile(r"^[\s.,;:!?\"()\[\]-]+|[\s.,;:!?\"()\[\]-]+$")
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*")


def normalize(text: str) -> str:
    text = text.lower().translate(_QUOTES)
    text = _DASHES.sub("-", text)
    text = _MARKUP.sub("", text)
    text = _SPACES.sub(" ", text)
    return _EDGE.sub("", text)


@dataclass
class QuoteMatch:
    ok: bool
    block_id: str
    quote: str
    exact: bool


def _fuzzy_ratio(quote: str, text: str) -> float:
    """Share of the quote covered by matching blocks against the best window of the text."""
    if not quote or not text:
        return 0.0
    sm = SequenceMatcher(None, text, quote, autojunk=False)
    covered = sum(m.size for m in sm.get_matching_blocks() if m.size >= 4)
    return covered / len(quote)


def _contains(quote_n: str, text_n: str) -> bool:
    parts = [p for p in _ELLIPSIS.split(quote_n) if p]
    return bool(parts) and all(normalize(p) in text_n for p in parts)


def verify_quote(doc: Document, block_id: str, quote: str, fuzzy_threshold: float = 0.85) -> QuoteMatch:
    quote_n = normalize(quote)
    if len(quote_n) < 3:
        return QuoteMatch(False, block_id, quote, False)

    block = doc.block(block_id)
    if block is not None and _contains(quote_n, normalize(block.text)):
        return QuoteMatch(True, block_id, quote, True)

    # Quote found in a different block: re-anchor it.
    for b in doc.blocks:
        if _contains(quote_n, normalize(b.text)):
            return QuoteMatch(True, b.id, quote, True)

    # Fuzzy: tolerate small paraphrase or punctuation drift inside the indicated block or its neighbours.
    candidates = []
    if block is not None:
        idx = doc.blocks.index(block)
        candidates = doc.blocks[max(0, idx - 2) : idx + 3]
    best_id, best_ratio = block_id, 0.0
    for b in candidates:
        ratio = _fuzzy_ratio(quote_n, normalize(b.text))
        if ratio > best_ratio:
            best_id, best_ratio = b.id, ratio
    if best_ratio >= fuzzy_threshold:
        fixed = doc.block(best_id)
        text = fixed.text if fixed and len(fixed.text) <= 300 else quote
        return QuoteMatch(True, best_id, text, False)
    return QuoteMatch(False, block_id, quote, False)
