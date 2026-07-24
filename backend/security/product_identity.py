"""Deterministic final-page product identity checks."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")
_GENERIC = {
    "the", "and", "with", "for", "from", "new", "pc", "computer", "desktop",
    "mini", "pro", "plus", "edition", "model",
}


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN.findall(value.casefold()) if len(token) > 1 and token not in _GENERIC}


def product_title_matches(expected: str, actual: str) -> bool:
    expected_tokens = _tokens(expected)
    actual_tokens = _tokens(actual)
    if not expected_tokens or not actual_tokens:
        return False
    distinctive = {token for token in expected_tokens if any(char.isdigit() for char in token) or len(token) >= 5}
    required = distinctive or expected_tokens
    overlap = expected_tokens & actual_tokens
    return required.issubset(actual_tokens) and len(overlap) / len(expected_tokens) >= 0.6
