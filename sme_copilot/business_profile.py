"""First-run setup: the owner says in their own words what the business sells; the AI Assistant works out the rest.

From the business name and that answer the model picks the closest business type (which chooses the Advanced home
layout and the default reminders), a short plain description (shown back to the owner and given to the AI Assistant as
the business's sector), and the market prices worth following. The model only chooses from fixed lists; the owner's
text is untrusted data. Without a model, keyword rules decide, so setup never waits on or fails because of the model.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable

from sme_copilot import home_layout as hl
from sme_copilot.llm_providers.base import Message
from sme_copilot.llm_providers.structured import extract_json
from sme_copilot.market import catalog, watch
from sme_copilot.security.injection import SYSTEM_GUARD, scan, wrap_untrusted

log = logging.getLogger(__name__)

LLM_TIMEOUT_S = 25.0
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="business-profile")

# Words in the name or answer -> business type, used when no model is available. First match wins.
TYPE_WORDS = [
    ("restaurant_food", ("cake", "bakery", "baker", "pastry", "sweet", "mishti", "restaurant", "hotel", "food", "biryani",
                         "tea", "cafe", "coffee", "catering", "snack", "fast food", "kitchen", "কেক", "বেকারি", "মিষ্টি",
                         "রেস্টুরেন্ট", "হোটেল", "খাবার", "চা")),
    ("pharmacy_grocery", ("pharmacy", "medicine", "grocery", "mudi", "mudir", "ওষুধ", "ফার্মেসি", "মুদি")),
    ("garments_trims", ("garment", "trims", "button", "zipper", "label", "fabric", "tailor", "boutique", "পোশাক", "দর্জি")),
    ("wholesale_trading", ("wholesale", "trading", "importer", "distributor", "dealer", "পাইকারি")),
    ("service_salon", ("salon", "parlour", "parlor", "beauty", "repair", "service", "servicing", "laundry", "সেলুন", "পার্লার", "মেরামত")),
    ("retail", ("shop", "store", "retail", "electronics", "mobile", "phone", "cosmetics", "dokan", "দোকান")),
]


def rule_type(*texts: str) -> str:
    blob = " ".join(t or "" for t in texts).lower()
    for key, words in TYPE_WORDS:
        if any((w in blob) if not w.isascii() else re.search(r"\b" + re.escape(w), blob) for w in words):
            return key
    return "other"


def _schema(allowed_items: list[str]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["business_type", "summary", "price_items"],
            "properties": {
                "business_type": {"type": "string", "enum": list(hl.BUSINESS_TYPES)},
                "summary": {"type": "string", "maxLength": 70},
                "price_items": {"type": "array", "minItems": watch.SUGGEST_MIN, "maxItems": watch.SUGGEST_MAX,
                                "items": {"type": "string", "enum": allowed_items}}}}


def _ask_model(provider: Any, name: str, about: str, chosen: str, allowed_items: list[str]) -> dict[str, Any]:
    types = "\n".join(f"- {k}: {v}" for k, v in hl.BUSINESS_TYPES.items())
    items = "\n".join(f"- {c}" for c in allowed_items)
    system = ("You set up a money app for a small business in Bangladesh. From the owner's own words, decide:\n"
              f"1. business_type: the closest of these ids:\n{types}\n"
              "2. summary: what the business does in at most 8 plain English words, e.g. \"home bakery selling custom cakes\".\n"
              f"3. price_items: {watch.SUGGEST_MIN}-{watch.SUGGEST_MAX} items from this list ONLY that the business buys to make or "
              f"sell its goods or to run the shop, most important first, names copied exactly:\n{items}\n"
              "Answer with JSON matching the schema, nothing else.\n" + SYSTEM_GUARD)
    user = ("Business name:\n" + wrap_untrusted("business_name", name) + "\nWhat the owner says the business sells or does:\n"
            + wrap_untrusted("about", about or "not given") + "\nType the owner picked (may be empty):\n" + wrap_untrusted("picked", chosen or ""))
    schema = _schema(allowed_items)
    msgs = [Message("system", system if provider.supports_json_mode else system + "\nJSON schema:\n" + json.dumps(schema)),
            Message("user", user)]
    resp = provider.chat(msgs, json_schema=schema if provider.supports_json_mode else None, temperature=0.0, max_tokens=500)
    raw = extract_json(resp.content)
    if not isinstance(raw, dict) or raw.get("business_type") not in hl.BUSINESS_TYPES:
        raise ValueError("model returned no business type")
    picked = watch.clean(raw.get("price_items"), allowed_items, watch.SUGGEST_MAX)
    if len(picked) < 2:
        raise ValueError("model picked no usable price items")
    return {"business_type": raw["business_type"], "summary": hl.clean_text(str(raw.get("summary") or ""), 70), "price_items": picked}


def profile(name: str, about: str, chosen: str | None = None, *,
            provider_factory: Callable[[], Any] | None = None, timeout: float = LLM_TIMEOUT_S) -> dict[str, Any]:
    """{"business_type", "summary", "price_items", "source": "ai" | "rules"}. Never raises."""
    chosen = chosen if chosen in hl.BUSINESS_TYPES and chosen != "other" else ""
    about = hl.clean_text(about or "", 200)
    bt = chosen or rule_type(name, about)
    fallback = {"business_type": bt, "summary": about[:70], "price_items": watch.rule_pick(name, bt, about), "source": "rules"}
    if not about or scan(f"{name} {about}").suspicious:  # nothing to read, or instruction-like text: rules only
        return fallback
    try:
        if provider_factory is None:
            from sme_copilot.llm_providers.registry import get_registry
            reg = get_registry()
            provider_factory = lambda: reg.get(reg.default_profile)  # noqa: E731
        provider = provider_factory()
        if getattr(provider, "adapter", "") == "rules":
            return fallback
        out = _pool.submit(_ask_model, provider, name, about, chosen, watch.available()).result(timeout=timeout)
    except FutureTimeout:
        log.info("business profile timed out after %.0fs; using rules", timeout)
        return fallback
    except Exception as e:  # noqa: BLE001 - any provider/parse failure -> rules
        log.info("business profile failed (%s); using rules", e)
        return fallback
    if chosen:  # the owner's own choice of type wins over the model's guess
        out["business_type"] = chosen
    out["price_items"] = watch.with_keywords(out["price_items"], name, about)
    if catalog.goods_without_prices(name, about):  # no public series for these goods: running costs, said plainly
        out["price_items"] = watch.clean(catalog.RUNNING_COSTS, watch.available())
    return {**out, "source": "ai"}
