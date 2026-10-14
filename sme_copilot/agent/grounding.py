"""Numeric grounding: every number in the reply must come from a tool result.

Extracts numbers from the reply (handles ৳, commas, lakh/crore words, %, Bangla digits) and
checks each against the numbers present in tool outputs (allowing rounding, lakh/crore scaling
and ratio<->percent conversion). Ungrounded numbers are surfaced to the user and counted as a
hallucination signal in the benchmark.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from sme_copilot.tools.textnorm import bn_to_ascii_digits

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(lakh|lac|crore|k\b|লাখ|কোটি|হাজার|hazar|thousand)?",
                  re.I)
_SCALE = {"lakh": 1e5, "lac": 1e5, "লাখ": 1e5, "crore": 1e7, "কোটি": 1e7, "k": 1e3, "হাজার": 1e3, "hazar": 1e3,
          "thousand": 1e3}


def extract_numbers(text: str) -> list[float]:
    text = bn_to_ascii_digits(text or "")
    # ignore ISO dates / dd/mm/yyyy and placeholders like [PHONE_1], INV-101
    text = re.sub(r"\b\d{4}-\d{2}(-\d{2})?\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\[[A-Z]+_\d+\]|\b[A-Z]{2,}-\d+\b", " ", text)
    out = []
    for m in _NUM.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        scale = _SCALE.get((m.group(2) or "").lower(), 1)
        out.append(v * scale)
    return out


def _walk(obj: Any) -> Iterable[float]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, str):
        yield from extract_numbers(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("row_ids",):
                continue
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def reference_numbers(tool_data: list[Any], user_text: str = "") -> set[float]:
    ref: set[float] = set()
    for d in tool_data:
        for v in _walk(d):
            for x in (v, abs(v)):
                ref.add(round(x, 2))
                ref.add(round(x))
                ref.add(round(x, 1))
                if abs(x) <= 1.5:  # ratios -> percentages
                    ref.add(round(x * 100, 1))
                    ref.add(round(x * 100))
                if abs(x) >= 1e5:  # lakh / crore words
                    ref.add(round(x / 1e5, 1))
                    ref.add(round(x / 1e5, 2))
                    ref.add(round(x / 1e7, 2))
                if abs(x) >= 1e3:
                    ref.add(round(x / 1e3, 1))
    for v in extract_numbers(user_text):
        ref.add(round(v, 2))
    return ref


def _close(v: float, ref: set[float]) -> bool:
    for r in ref:
        tol = max(0.51, abs(r) * 0.005)
        if abs(v - r) <= tol:
            return True
    return False


def ungrounded_numbers(reply: str, tool_data: list[Any], user_text: str = "") -> list[float]:
    ref = reference_numbers(tool_data, user_text)
    bad = []
    for v in extract_numbers(reply):
        if v <= 31 and float(v).is_integer():
            continue  # day counts, months, list numbering
        if 1990 <= v <= 2100 and float(v).is_integer():
            continue  # years
        if v in (60, 90, 100, 120, 180, 365):
            continue  # horizons and common constants
        if not _close(v, ref):
            bad.append(v)
    return bad
