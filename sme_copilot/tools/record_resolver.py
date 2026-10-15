"""Free-text record reading: the LLM (or a regex fast path) only EXTRACTS fields; Python computes amount and sign.

    read_record(text) -> (extracted | None, source)      fast path, else cached/queued LLM call
    resolve_record(extracted) -> {amount, signed_amount, direction, category, needs_confirm, reason, preview}
"""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from .textnorm import normalize

TYPES = ["sale", "purchase", "expense", "sale_return", "purchase_return", "payment_received", "payment_made"]
CATEGORIES = ["sales", "sales_returns", "rent", "salary", "packaging", "transport", "utilities", "mobile_fees",
              "purchases", "loan_payment", "other"]
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"enum": TYPES},
        "item": {"type": ["string", "null"]},
        "quantity": {"type": ["number", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "total_stated": {"type": ["number", "null"]},
        "counterparty": {"type": ["string", "null"]},
        "category": {"enum": CATEGORIES},
        "payment_method": {"enum": ["cash", "bkash", "bank", "credit", "unknown"]},
    },
    "required": ["type", "item", "quantity", "unit_price", "total_stated", "counterparty", "category",
                 "payment_method"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Extract ONE bookkeeping record from Bangla, English or Banglish text as JSON. Convert Bangla digits to ASCII.
Never compute totals. Never output negative numbers. Output only JSON.
- "each" words (protitar, prottek, protita, per piece, each, kore, dor) => number goes in unit_price.
- One amount with NO per-unit cue => total_stated. Quantity and a total both given => fill both.
- bikri/sold/becha => sale. kinlam/kena/bought => purchase. dilam/paid/vara/bill => expense.
- ferot/return/refund/"ferot diye gese" (customer gave goods back) => sale_return.
  "supplier ke ferot dilam" (we returned goods to a supplier) => purchase_return. payment pailam/received => payment_received.
Examples:
"6 ta gamcha bikri korci protitar dam 100 taka kore" -> {"type":"sale","item":"gamcha","quantity":6,"unit_price":100,"total_stated":null,"counterparty":null,"category":"sales","payment_method":"unknown"}
"2 ta jama ferot diye gese 1500 taka" -> {"type":"sale_return","item":"jama","quantity":2,"unit_price":null,"total_stated":1500,"counterparty":null,"category":"sales_returns","payment_method":"unknown"}
"dokan vara 10000 taka dilam" -> {"type":"expense","item":"dokan vara","quantity":null,"unit_price":null,"total_stated":10000,"counterparty":null,"category":"rent","payment_method":"unknown"}
"supplier ke 3 ta thaan ferot dilam 4500 taka" -> {"type":"purchase_return","item":"thaan","quantity":3,"unit_price":null,"total_stated":4500,"counterparty":"supplier","category":"purchases","payment_method":"unknown"}"""

# money direction per record type (+1 in, -1 out)
SIGN = {"sale": 1, "payment_received": 1, "purchase_return": 1,
        "expense": -1, "sale_return": -1, "payment_made": -1, "purchase": -1}
# extraction category -> stored category (config/categories.yaml)
STORE_CATEGORY = {"purchases": "inventory", "loan_payment": "loan_repayment", "other": "uncategorized"}
FORCED_CATEGORY = {"sale": "sales", "sale_return": "sales_returns", "purchase_return": "purchase_returns"}
LABEL = {"sale": "Sold", "purchase": "Bought", "expense": "Expense", "sale_return": "Customer return",
         "purchase_return": "Returned to supplier", "payment_received": "Payment received",
         "payment_made": "Payment made"}
MAX_AMOUNT = 1_000_000


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


def resolve_record(ex: dict) -> dict:
    typ = ex.get("type")
    qty, unit, total = _num(ex.get("quantity")), _num(ex.get("unit_price")), _num(ex.get("total_stated"))
    computed = qty * unit if qty is not None and unit is not None else None
    reasons: list[str] = []
    if total is not None:
        amount = total
        if computed is not None and abs(computed - total) > 0.01:
            reasons.append(f"stated total {_fmt(total)} differs from {_fmt(qty)} x {_fmt(unit)} = {_fmt(computed)}")
    else:
        amount = computed
    if typ not in SIGN:
        reasons.append("unknown record type")
    if amount is None:
        reasons.append("no amount found")
    elif amount <= 0:
        reasons.append("amount must be positive")
    elif amount > MAX_AMOUNT:
        reasons.append("amount is very large")
    if qty is not None and qty <= 0:
        reasons.append("quantity must be positive")
    cat = ex.get("category") or "other"
    if typ in FORCED_CATEGORY:
        cat = FORCED_CATEGORY[typ]
    elif cat == "other":
        reasons.append("category unclear")
    sign = SIGN.get(typ, 0)
    ok = amount is not None and amount > 0 and sign != 0
    signed = sign * amount if ok else None
    item = ex.get("item") or ""
    if not ok:
        preview = "Could not work out the amount."
    else:
        calc = f"{_fmt(qty)} {item} x {_fmt(unit)} = {_fmt(amount)}" if computed is not None and total is None \
            else f"{_fmt(qty)} {item} = {_fmt(amount)}" if qty is not None else f"{item} {_fmt(amount)}".strip()
        preview = f"{LABEL[typ]} {calc} ({'money in' if sign > 0 else 'money out'}). Save?"
    return {"type": typ, "amount": amount, "signed_amount": signed, "direction": "in" if sign > 0 else "out",
            "quantity": qty, "unit_price": unit, "item": item, "counterparty": ex.get("counterparty") or "",
            "category": STORE_CATEGORY.get(cat, cat), "channel": _channel(ex.get("payment_method")),
            "needs_confirm": bool(reasons), "reason": "; ".join(reasons), "preview": preview}


def _channel(pm: str | None) -> str:
    return pm if pm in ("cash", "bkash", "bank") else "cash"


# ---------------------------------------------------------------- fast path
_N = r"(\d+(?:\.\d+)?)"
_RETURN_WORDS = re.compile(r"ferot|ferat|return|refund|ফেরত")
_EACH = re.compile(r"\b(protitar|protita|prottek\w*|protek\w*|per piece|each|dor|kore)\b")
_SOLD_FOR = re.compile(rf"^sold {_N} (?P<item>[a-z][a-z ]*?) for {_N} ?(?:taka|tk)\b")
_BIKRI = re.compile(rf"^{_N} ?(?:ta|ti|pcs|pc|piece|pieces)? ?(?P<item>[a-z][a-z ]*?) (?:bikri|becha|bechlam)\b.*?{_N} ?(?:taka|tk)\b")
_EXPENSE_WORD = re.compile(r"\b(dilam|diyechi|paid|vara|bhara|rent|bill|beton|salary|khoroch)\b")
_AMOUNT_ONLY = re.compile(rf"{_N} ?(?:taka|tk)\b")
_EXP_CATS = [(r"\b(vara|bhara|rent)\b", "rent"), (r"\b(beton|salary)\b", "salary"),
             (r"\b(bill|bijli|current|gas|internet)\b", "utilities"), (r"\b(courier|transport|gari)\b", "transport")]


def fast_path(text: str) -> dict | None:
    t = normalize(text).replace(",", "")
    if not t or _RETURN_WORDS.search(t) or re.search(r"\b(kinlam|kena|bought|supplier|pailam|received)\b", t):
        return None
    base = {"item": None, "quantity": None, "unit_price": None, "total_stated": None, "counterparty": None,
            "category": "sales", "payment_method": "unknown"}
    m = _SOLD_FOR.match(t)
    if m:
        return {**base, "type": "sale", "quantity": float(m.group(1)), "item": m.group("item").strip(),
                "total_stated": float(m.group(3))}
    m = _BIKRI.match(t)
    if m:
        key = "unit_price" if _EACH.search(t) else "total_stated"
        return {**base, "type": "sale", "quantity": float(m.group(1)), "item": m.group("item").strip(),
                key: float(m.group(3))}
    amounts = _AMOUNT_ONLY.findall(t)
    if len(amounts) == 1 and len(re.findall(r"\d+", t)) == 1 and _EXPENSE_WORD.search(t) \
            and not re.search(r"\b(bikri|sold|becha)\b", t):
        cat = next((c for rx, c in _EXP_CATS if re.search(rx, t)), "other")
        return {**base, "type": "expense", "category": cat, "total_stated": float(amounts[0]),
                "item": re.sub(rf"{_N} ?(?:taka|tk)\b|\b(dilam|diyechi|paid)\b", "", t).strip() or None}
    return None


# ---------------------------------------------------------------- LLM path: one queue, timeout, retry-once, cache
LLM_TIMEOUT_S = 20
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="record-llm")  # single queue: calls run one at a time
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 512


def _llm_extract(text: str) -> dict:
    from sme_copilot.llm_providers.base import Message
    from sme_copilot.llm_providers.registry import get_router
    from sme_copilot.llm_providers.structured import extract_json
    resp = get_router().chat([Message("system", SYSTEM_PROMPT), Message("user", text)], task="extraction",
                             json_schema=EXTRACTION_SCHEMA, temperature=0.0, max_tokens=300).response
    ex = extract_json(resp.content)
    if not isinstance(ex, dict) or ex.get("type") not in TYPES:
        raise ValueError("invalid extraction")
    if ex.get("category") not in CATEGORIES:
        ex["category"] = "other"
    return ex


def read_record(text: str) -> tuple[dict | None, str]:
    """-> (extracted, source) with source in fast|llm|cache; (None, 'failed') when the LLM cannot read the text."""
    ex = fast_path(text)
    if ex:
        return ex, "fast"
    key = normalize(text)
    with _cache_lock:
        if key in _cache:
            return dict(_cache[key]), "cache"
    for _ in range(2):  # first try + retry once
        try:
            ex = _pool.submit(_llm_extract, text).result(timeout=LLM_TIMEOUT_S)
        except (FutureTimeout, Exception):  # noqa: BLE001 - any provider/parse failure -> retry, then give up
            continue
        with _cache_lock:
            if len(_cache) >= _CACHE_MAX:
                _cache.pop(next(iter(_cache)))
            _cache[key] = ex
        return dict(ex), "llm"
    return None, "failed"


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


