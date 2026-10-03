"""Deterministic amount parsing: '1,250.00 DR' -> 1250.0, '2,499.00 CR' -> -2499.0.

LLM for judgement, code for rules: turning text into numbers is a rule, so code
does it and overrides whatever the model returned.
"""
from __future__ import annotations

import re

_AMOUNT_AT_END = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*(DR|CR)?\s*$", re.IGNORECASE)


def parse_amount(line: str) -> float | None:
    """Amount at the end of a statement line. DR = positive (money out), CR = negative (money in).
    No marker -> keep the sign as written. Returns None if no amount is found."""
    match = _AMOUNT_AT_END.search(line.strip())
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    marker = (match.group(2) or "").upper()
    if marker == "DR":
        return abs(value)
    if marker == "CR":
        return -abs(value)
    return value


def enforce_amounts(text: str, result) -> int:
    """Overwrite model amounts with parsed ones when the input is one transaction per line.
    Returns how many amounts the model got WRONG (useful metric). Skips silently when the
    input is not line-per-transaction (e.g. 'Swiggy 450, Uber 230' on one line)."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or len(lines) != len(result.transactions):
        return 0
    fixes = 0
    for line, txn in zip(lines, result.transactions):
        parsed = parse_amount(line)
        if parsed is not None and abs(parsed - txn.amount) > 0.005:
            txn.amount = parsed
            fixes += 1
    return fixes
