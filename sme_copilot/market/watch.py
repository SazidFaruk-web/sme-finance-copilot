"""Which items an owner follows in the price drawer.

On first open the AI Assistant picks items from the business name, type and description (the model chooses only
from published series; it cannot invent an item or a price). Without a model, words in the name and the business
type decide. The owner can then remove items or add any other published item; that list is saved per user.
"""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable

import pandas as pd

from sme_copilot.llm_providers.base import Message
from sme_copilot.llm_providers.structured import extract_json
from sme_copilot.security.injection import SYSTEM_GUARD, scan, wrap_untrusted

from . import catalog, prices
from .service import FRESH_MONTHS

log = logging.getLogger(__name__)

MAX_ITEMS = 20  # an owner's own list
SUGGEST_MIN, SUGGEST_MAX = 4, 8
LLM_TIMEOUT_S = 25.0

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="market-suggest")
_avail_lock = threading.Lock()
_avail: tuple[str, list[str]] | None = None


def available() -> list[str]:
    """Published items with data recent enough to show (same freshness rule as the drawer), most common first."""
    global _avail
    data = prices.load()
    with _avail_lock:
        if _avail and _avail[0] == data.version:
            return list(_avail[1])
    frame = data.frame
    fresh_from = (pd.Period(frame["date"].max(), freq="M") - FRESH_MONTHS).to_timestamp()
    latest = frame.groupby("commodity")["date"].max()
    known = [c for c in catalog.ITEMS if c in latest.index and latest[c] >= fresh_from]
    with _avail_lock:
        _avail = (data.version, known)
    return list(known)


def catalog_rows(lang_items: list[str] | None = None) -> list[dict[str, Any]]:
    return [{"id": c, "label": catalog.label(c)} for c in (lang_items if lang_items is not None else available())]


def clean(items: Any, allowed: list[str], cap: int = MAX_ITEMS) -> list[str]:
    out: list[str] = []
    for i in items if isinstance(items, list) else []:
        if isinstance(i, str) and i in allowed and i not in out:
            out.append(i)
    return out[:cap]


def rule_pick(name: str, business_type: str | None, text: str = "") -> list[str]:
    allowed = available()
    if catalog.goods_without_prices(name, text, (business_type or "").replace("_", " ")):
        return clean(catalog.RUNNING_COSTS, allowed, SUGGEST_MAX)
    words = catalog.keyword_basket(name, text, (business_type or "").replace("_", " "))
    _, basket = catalog.basket(business_type)
    picked = clean(words, allowed, SUGGEST_MAX) if words else []
    if len(picked) < SUGGEST_MIN:
        picked = clean(picked + basket, allowed, SUGGEST_MAX)
    return picked


def with_keywords(items: list[str], *texts: str) -> list[str]:
    """The model's picks first, then items the business's own words clearly call for (a cake shop always gets flour)."""
    return clean(items + catalog.keyword_basket(*texts), available(), SUGGEST_MAX)


def _schema(allowed: list[str]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["items", "reason"], "properties": {
        "items": {"type": "array", "minItems": SUGGEST_MIN, "maxItems": SUGGEST_MAX, "items": {"type": "string", "enum": allowed}},
        "reason": {"type": "string", "maxLength": 160}}}


def _ask_model(provider: Any, name: str, business_type: str, text: str, allowed: list[str]) -> tuple[list[str], str]:
    listing = "\n".join(f"- {c}" for c in allowed)
    system = ("You help a small business in Bangladesh follow the market prices that matter to it. From the list "
              f"below ONLY, pick {SUGGEST_MIN}-{SUGGEST_MAX} items the business buys to make or sell its goods, or to run "
              "the shop, most important first. Copy item names exactly. Give a one-line reason in plain English. "
              f"Answer with JSON matching the schema, nothing else.\nItems:\n{listing}\n" + SYSTEM_GUARD)
    user = ("Business name:\n" + wrap_untrusted("business_name", name) + "\nBusiness type:\n"
            + wrap_untrusted("business_type", business_type or "not given")
            + ("\nDescription:\n" + wrap_untrusted("description", text) if text else ""))
    schema = _schema(allowed)
    msgs = [Message("system", system if provider.supports_json_mode else system + "\nJSON schema:\n" + json.dumps(schema)),
            Message("user", user)]
    resp = provider.chat(msgs, json_schema=schema if provider.supports_json_mode else None, temperature=0.0, max_tokens=500)
    raw = extract_json(resp.content)
    items = clean(raw.get("items") if isinstance(raw, dict) else None, allowed, SUGGEST_MAX)
    if len(items) < 2:
        raise ValueError("model picked no usable items")
    reason = str(raw.get("reason") or "")[:160] if isinstance(raw, dict) else ""
    return items, reason


def suggest(name: str, business_type: str | None, text: str = "", *,
            provider_factory: Callable[[], Any] | None = None, timeout: float = LLM_TIMEOUT_S) -> dict[str, Any]:
    """{"items", "source": "ai" | "rules", "reason"}. Never raises: any model problem falls back to the rules."""
    fallback = {"items": rule_pick(name, business_type, text), "source": "rules", "reason": ""}
    if scan(f"{name} {text}").suspicious:  # instruction-like text is never sent to the model
        return fallback
    try:
        if provider_factory is None:
            from sme_copilot.llm_providers.registry import get_registry
            reg = get_registry()
            provider_factory = lambda: reg.get(reg.default_profile)  # noqa: E731
        provider = provider_factory()
        if getattr(provider, "adapter", "") == "rules":
            return fallback
        items, reason = _pool.submit(_ask_model, provider, name, business_type or "", text, available()).result(timeout=timeout)
    except FutureTimeout:
        log.info("price item suggestion timed out after %.0fs; using rules", timeout)
        return fallback
    except Exception as e:  # noqa: BLE001 - any provider/parse failure -> rules
        log.info("price item suggestion failed (%s); using rules", e)
        return fallback
    if catalog.goods_without_prices(name, text, business_type or ""):
        items = clean(catalog.RUNNING_COSTS, available(), SUGGEST_MAX)
    return {"items": with_keywords(items, name, text), "source": "ai", "reason": reason}
