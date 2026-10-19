"""Rule-based transaction categorisation (multilingual keywords; LLM is an optional fallback)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sme_copilot.config import load_yaml

from .textnorm import contains_keyword, normalize


@dataclass
class CategoryMatch:
    category: str
    confidence: float
    keyword: str = ""
    direction: str | None = None


# "bought 200 switch board from bright light 17000": a buying verb plus a quantity and a separate amount is stock bought
# for resale, even when the item is not a keyword (the owner's own catalogue is not known here).
_BUY_VERB = re.compile(r"(?<![a-z])(bought|purchased|kinlam|kinechi|kinsi|kinlm)(?![a-z])|কিনলাম|কিনেছি")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _looks_like_stock_purchase(norm: str) -> bool:
    return bool(_BUY_VERB.search(norm)) and len(_NUMBER.findall(norm)) >= 2


@lru_cache
def category_config() -> dict[str, Any]:
    return load_yaml("categories.yaml")


def categories() -> dict[str, dict[str, Any]]:
    return category_config()["categories"]


def behavior(category: str) -> str:
    return categories().get(category, {}).get("behavior", "variable")


def category_direction(category: str) -> str | None:
    return categories().get(category, {}).get("direction")


@lru_cache
def _keyword_index() -> list[tuple[str, str]]:
    """(keyword, category) sorted longest-first so specific phrases win."""
    pairs: list[tuple[str, str]] = []
    for cat, spec in categories().items():
        for lang_list in (spec.get("keywords") or {}).values():
            for kw in lang_list or []:
                pairs.append((str(kw), cat))
    pairs.sort(key=lambda p: len(normalize(p[0])), reverse=True)
    return pairs


def categorize(text: str, direction: str | None = None) -> CategoryMatch:
    """Return the best category for free text. If ``direction`` is known, categories of the
    other direction are skipped (a 'rent' keyword on an inflow is not rent paid)."""
    return CategoryMatch(*_categorize(text, direction))


@lru_cache(maxsize=8192)  # statements repeat the same narrations thousands of times
def _categorize(text: str, direction: str | None) -> tuple[str, float, str, str | None]:
    norm = normalize(text)
    if not norm:
        return "uncategorized", 0.0, "", None
    for kw, cat in _keyword_index():
        cat_dir = category_direction(cat)
        if direction and cat_dir and cat_dir != direction:
            continue
        if contains_keyword(norm, kw):
            # Longer keyword = more specific = more confident.
            conf = min(0.95, 0.6 + 0.05 * len(normalize(kw).split()) + 0.01 * len(normalize(kw)))
            return cat, round(conf, 2), kw, cat_dir
    if direction in (None, "out") and _looks_like_stock_purchase(norm):
        return "inventory", 0.6, "", "out"
    if direction == "in":
        return "sales", 0.4, "", "in"  # most unlabelled SME inflows are sales
    return "uncategorized", 0.0, "", direction


def detect_direction(text: str) -> tuple[str | None, str]:
    """Infer in/out. Explicit verbs ("sold", "paid", "dilam", "বিক্রি") win over item/category keywords,
    so "sold 40 zippers" is income even though "zippers" is an inventory keyword."""
    norm = normalize(text)
    words = category_config().get("direction_words", {})
    best: tuple[int, str | None, str] = (0, None, "")
    for d in ("in", "out"):
        for lang_list in (words.get(d) or {}).values():
            for kw in lang_list or []:
                if contains_keyword(norm, kw) and len(kw) > best[0]:
                    best = (len(kw), d, kw)
    if best[1]:
        return best[1], best[2]
    m = categorize(text)
    if m.direction and m.category != "uncategorized":
        return m.direction, m.keyword
    return None, ""


def all_category_names() -> list[str]:
    return list(categories().keys()) + ["uncategorized"]
