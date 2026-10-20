"""What the thing is likely to cost, when the owner has not been given a quote.

Three sources, in order of trust:

* ``owner``   - a price the owner typed or a quote they hold. Always wins.
* ``web``     - a trimmed average of taka figures found in public search results. Only on an explicit
                request from the owner, never in LOCAL_ONLY_MODE, and never without the operator
                switch. The item wording leaves the machine; nothing else does.
* ``catalog`` - a reviewed, dated range from ``config/goal_prices.yaml`` for common purchases.

Every estimate is shown to the owner as a range they can replace. None of them is a quote.
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any
from urllib.parse import quote_plus

from sme_copilot.config import get_settings, load_yaml

LOG = logging.getLogger(__name__)

# A figure in a search snippet: "Tk 2,50,000", "৳250000", "250000 BDT", "2.5 lakh".
_FIGURE = re.compile(
    r"(?:৳|tk\.?|bdt|taka|টাকা)\s*([\d,]+(?:\.\d+)?)"
    r"|([\d,]+(?:\.\d+)?)\s*(?:৳|tk\.?\b|bdt|taka|টাকা)"
    r"|([\d.]+)\s*(?:lakhs?|lacs?|লাখ)", re.I)
_TAG = re.compile(r"<[^>]+>")


@dataclass
class PriceEstimate:
    amount: float | None = None
    low: float | None = None
    high: float | None = None
    source: str = "unknown"        # owner | web | catalog | unknown
    label: dict[str, str] = field(default_factory=dict)   # what the range describes
    note: dict[str, str] = field(default_factory=dict)    # the caveat shown with it
    samples: int = 0               # how many listings the web average used
    reviewed: str = ""             # the date a human last checked a catalog range

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    try:
        return load_yaml("goal_prices.yaml") or {}
    except (OSError, ValueError):
        LOG.warning("goal_prices.yaml is missing or unreadable; catalog prices are unavailable")
        return {}


def catalog_price(item: str, specification: str = "") -> PriceEstimate | None:
    """The reviewed range for a common purchase, or None when the item is not in the catalog."""
    data = _catalog()
    text = f"{item} {specification}".strip()
    if not text:
        return None
    for row in data.get("items", []):
        try:
            if re.search(row["match"], text, re.I):
                low, high = float(row["low"]), float(row["high"])
                return PriceEstimate(amount=round((low + high) / 2, 2), low=low, high=high, source="catalog",
                                     label=row.get("label", {}), note=data.get("note", {}),
                                     reviewed=str(data.get("reviewed", "")))
        except (re.error, KeyError, TypeError, ValueError):
            continue
    return None


def lookup_available() -> bool:
    """Whether an online price lookup can be offered at all."""
    s = get_settings()
    return bool(s.goal_price_lookup and not s.local_only_mode and s.goal_price_search_url)


def _figures(text: str) -> list[float]:
    out: list[float] = []
    for taka_before, taka_after, lakh in _FIGURE.findall(text):
        raw = taka_before or taka_after or lakh
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if lakh:
            value *= 100_000
        if 500 <= value <= 50_000_000:
            out.append(value)
    return out


def _trimmed_average(values: list[float]) -> tuple[float, float, float] | None:
    """Average of the middle of the distribution, with the range it came from.

    Search results mix accessories with the machine itself, so the outer quarter at each end is
    dropped before averaging. Fewer than three figures is not an average worth showing.
    """
    values = sorted(v for v in values if v > 0)
    if len(values) < 3:
        return None
    cut = len(values) // 4
    middle = values[cut:len(values) - cut] or values
    return round(statistics.fmean(middle), 2), middle[0], middle[-1]


def web_price(query: str, *, client: Any = None) -> PriceEstimate | None:
    """A trimmed average of taka figures publicly advertised for this item.

    The caller has already established that the owner asked for this. Returns None when the lookup
    is switched off, unreachable, or produced too few figures to average.
    """
    if not lookup_available() or not query.strip():
        return None
    import httpx

    s = get_settings()
    url = s.goal_price_search_url.replace("{query}", quote_plus(f"{query.strip()} price in Bangladesh"))
    try:
        http = client or httpx.Client(timeout=12, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0 (compatible; sme-copilot/goal-prices)"})
        with http as session:
            response = session.get(url)
            response.raise_for_status()
            text = _TAG.sub(" ", response.text)[:400_000]
    except Exception:  # noqa: BLE001 - an unavailable lookup falls back to the catalog, never an error page
        LOG.info("goal price lookup failed for %r", query[:60])
        return None
    averaged = _trimmed_average(_figures(text))
    if not averaged:
        return None
    amount, low, high = averaged
    return PriceEstimate(
        amount=amount, low=low, high=high, source="web", samples=len(_figures(text)),
        label={"en": f"Average of public listings for “{query.strip()}”",
               "bn": f"“{query.strip()}”-এর প্রকাশিত দামের গড়",
               "zh": f"“{query.strip()}”公开报价的平均值"},
        note={"en": "A rough average of prices advertised online, not a quote. Confirm with a supplier before you commit.",
              "bn": "অনলাইনে বিজ্ঞাপিত দামের মোটামুটি গড়, কোনো প্রস্তাব নয়। সিদ্ধান্তের আগে সরবরাহকারীর কাছে যাচাই করুন।",
              "zh": "网上广告价格的粗略平均值，不是报价。决定前请向供应商确认。"})


def estimate(item: str, specification: str = "", *, amount: float | None = None,
             search: bool = False, client: Any = None) -> PriceEstimate:
    """The best price available for this goal, with its source and caveat attached."""
    if amount is not None and amount > 0:
        return PriceEstimate(amount=round(float(amount), 2), source="owner",
                             note={"en": "Your own figure. Keep the written quote with your records.",
                                   "bn": "আপনার নিজের দেওয়া অঙ্ক। লিখিত প্রস্তাবটি হিসাবের সঙ্গে রাখুন।",
                                   "zh": "您自己填写的金额。请将书面报价与记录一并保存。"})
    if search:
        found = web_price(f"{item} {specification}".strip(), client=client)
        if found:
            return found
    return catalog_price(item, specification) or PriceEstimate(
        note={"en": "We could not estimate a price for this. Enter what it costs, or ask a supplier first.",
              "bn": "এর দাম অনুমান করা যায়নি। দামটি লিখুন, বা আগে সরবরাহকারীকে জিজ্ঞাসা করুন।",
              "zh": "无法估算此项价格。请填写价格，或先询问供应商。"})
