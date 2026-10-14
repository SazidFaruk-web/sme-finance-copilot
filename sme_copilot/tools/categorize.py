"""Rule-based transaction categorisation (multilingual keywords; LLM is an optional fallback)."""
from __future__ import annotations

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
    norm = normalize(text)
    if not norm:
        return CategoryMatch("uncategorized", 0.0)
    for kw, cat in _keyword_index():
        cat_dir = category_direction(cat)
        if direction and cat_dir and cat_dir != direction:
            continue
        if contains_keyword(norm, kw):
            # Longer keyword = more specific = more confident.
            conf = min(0.95, 0.6 + 0.05 * len(normalize(kw).split()) + 0.01 * len(normalize(kw)))
            return CategoryMatch(cat, round(conf, 2), kw, cat_dir)
    if direction == "in":
        return CategoryMatch("sales", 0.4, "", "in")  # most unlabelled SME inflows are sales
    return CategoryMatch("uncategorized", 0.0, "", direction)


def detect_direction(text: str) -> tuple[str | None, str]:
    """Infer in/out from category keywords first, then generic direction words."""
    m = categorize(text)
    if m.direction and m.category != "uncategorized":
        return m.direction, m.keyword
    norm = normalize(text)
    words = category_config().get("direction_words", {})
    best: tuple[int, str | None, str] = (0, None, "")
    for d in ("in", "out"):
        for lang_list in (words.get(d) or {}).values():
            for kw in lang_list or []:
                if contains_keyword(norm, kw) and len(kw) > best[0]:
                    best = (len(kw), d, kw)
    return best[1], best[2]


def all_category_names() -> list[str]:
    return list(categories().keys()) + ["uncategorized"]
