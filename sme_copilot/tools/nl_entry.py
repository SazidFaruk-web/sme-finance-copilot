"""Deterministic parser for quick natural-language bookkeeping entries.

Examples it understands:
    "sold 12 shirts for 6000 taka cash"
    "paid shop rent 15000"
    "১২টা শার্ট বিক্রি করলাম ৬০০০ টাকায়"
    "dokan bhara 15k dilam bkash e"
    "received 25,000 from Karim Traders via bank yesterday"

When confidence is low the agent may ask an LLM for structured extraction (validated by the
same ``ParsedEntry`` schema); this parser is always tried first and is fully offline.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from .categorize import categorize, detect_direction
from .textnorm import bn_to_ascii_digits, normalize

MULTIPLIERS = {
    "k": 1_000, "thousand": 1_000, "hazar": 1_000, "hajar": 1_000, "হাজার": 1_000,
    "lakh": 100_000, "lac": 100_000, "lakhs": 100_000, "lacs": 100_000, "লাখ": 100_000, "লক্ষ": 100_000,
    "crore": 10_000_000, "কোটি": 10_000_000,
}
CURRENCY_AFTER = ("taka", "tk", "টাকা", "bdt", "/-")
CURRENCY_BEFORE = ("৳", "tk", "tk.", "bdt", "taka")
QTY_MARKERS = ("pcs", "pc", "piece", "pieces", "ta", "ti", "টা", "টি", "units", "unit", "dozen", "doz", "kg",
               "gaj", "গজ", "jon", "জন", "yard", "yards", "meter", "meters", "box", "boxes", "bags", "bag", "packet", "packets")
PREP_BEFORE_AMOUNT = ("for", "at", "of", "=", "dam", "daam", "worth")

CHANNELS = [
    ("bkash", ("bkash", "bikash", "বিকাশ")),
    ("nagad", ("nagad",)),  # Latin "nagad" = the wallet; Bangla "নগদ" means cash (see ASSUMPTIONS.md)
    ("rocket", ("rocket", "রকেট")),
    ("bank", ("bank", "ব্যাংক", "cheque", "check", "bank transfer", "npsb", "beftn")),
    ("card", ("card", "কার্ড")),
    ("cash", ("cash", "nogod", "নগদ", "hand cash", "haate", "হাতে")),
]

_NUM = re.compile(
    r"(?P<pre>৳|tk\.?|bdt)?\s*(?P<num>\d+(?:,\d+)*(?:\.\d+)?)\s*"
    r"(?P<mult>k\b|thousand|hazar|hajar|হাজার|lakhs?|lacs?|লাখ|লক্ষ|crore|কোটি)?", re.I)

_PHONE_RX = re.compile(r"(?<![\d+])(?:\+?880[-\s]?|0)1[3-9]\d{2}[-\s]?\d{6}(?!\d)|\b\d{11,}\b")

_DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
]
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_DAY_MONTH = re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b")
_MONTH_DAY = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b")

_RELATIVE = [
    (("day before yesterday", "porshu", "parshu", "পরশু"), -2),
    (("yesterday", "gotokal", "gatokal", "গতকাল", "kal", "কাল"), -1),
    (("today", "aj", "aaj", "আজ"), 0),
]

_NAME_STOP = {"taka", "tk", "for", "via", "by", "cash", "bkash", "nagad", "rocket", "bank", "on", "the", "a", "and",
              "yesterday", "today", "e", "te", "diye", "kore", "payment", "in", "with", "dilam", "pelam", "korlam", "jon"}
_PARTY_PATTERNS = [
    re.compile(r"\bfrom\s+([a-z][\w&.'-]*(?:\s+[a-z][\w&.'-]*){0,3})"),
    re.compile(r"\bto\s+([a-z][\w&.'-]*(?:\s+[a-z][\w&.'-]*){0,3})"),
    re.compile(r"([a-z][\w&.'-]*(?:\s+[a-z][\w&.'-]*){0,2})\s+(?:ke|theke|er kach theke)\b"),
    re.compile(r"(\S+)\s*(?:কে|থেকে|এর কাছ থেকে)"),
]


@dataclass
class ParsedEntry:
    amount: float | None
    direction: str | None
    category: str
    channel: str
    txn_date: str  # ISO date
    counterparty: str = ""
    quantity: float | None = None
    item: str = ""
    description: str = ""
    confidence: float = 0.0
    missing: list[str] = field(default_factory=list)
    matched_keyword: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_amount_and_qty(norm: str) -> tuple[float | None, float | None, str]:
    candidates: list[dict] = []
    # Dates and phone / account numbers are not amounts: blank them out before scanning numbers.
    for pat, _ in _DATE_PATTERNS:
        norm = pat.sub(" ", norm)
    norm = _PHONE_RX.sub(" ", norm)
    for m in _NUM.finditer(norm):
        raw = m.group("num")
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        mult_word = (m.group("mult") or "").lower()
        mult = MULTIPLIERS.get(mult_word, 1)
        rest = norm[m.end():].strip()
        after = rest.split(" ", 2)[0] if rest else ""
        if after in ("ta", "ti", "pcs", "pc", "টা", "টি") and len(rest.split(" ")) > 1:
            after = " ".join(rest.split(" ", 2)[:2])
        before = norm[max(0, m.start() - 8):m.start()].strip().split()
        prev_word = before[-1] if before else ""
        is_currency = bool(m.group("pre")) or after.startswith(CURRENCY_AFTER) or prev_word in CURRENCY_BEFORE
        is_qty = (not mult_word) and (after.startswith(QTY_MARKERS) or norm[m.end():m.end() + 2] in ("টা", "টি"))
        candidates.append({"val": val * mult, "currency": is_currency, "qty": is_qty, "after": after,
                           "prep": prev_word in PREP_BEFORE_AMOUNT, "mult": bool(mult_word)})
    if not candidates:
        return None, None, ""
    money = [c for c in candidates if c["currency"] or c["mult"]] or [c for c in candidates if c["prep"]]
    if not money:
        non_qty = [c for c in candidates if not c["qty"]]
        money = non_qty or candidates
        if len(candidates) > 1 and not non_qty:
            money = [max(candidates, key=lambda c: c["val"])]
    amount = max(money, key=lambda c: c["val"])["val"]
    qty_c = [c for c in candidates if c["val"] != amount and (c["qty"] or len(candidates) > 1)]
    qty = qty_c[0]["val"] if qty_c else None
    item = ""
    if qty_c:
        item = re.sub(r"^(টা|টি|ta|ti|pcs|pc|pieces|piece)\s*", "", qty_c[0]["after"]).strip(" ,.")
    return amount, qty, item


def _extract_date(norm: str, today: date) -> date:
    for pat, kind in _DATE_PATTERNS:
        m = pat.search(norm)
        if m:
            try:
                a, b, c = (int(x) for x in m.groups())
                return date(c, b, a) if kind == "dmy" else date(a, b, c)
            except ValueError:
                pass
    m = _DAY_MONTH.search(norm) or _MONTH_DAY.search(norm)
    if m:
        g = m.groups()
        day, mon = (int(g[0]), _MONTHS[g[1][:3]]) if g[0].isdigit() else (int(g[1]), _MONTHS[g[0][:3]])
        try:
            d = date(today.year, mon, day)
            return d if d <= today else date(today.year - 1, mon, day)
        except ValueError:
            pass
    for words, delta in _RELATIVE:
        for w in words:
            if (w in norm) if any(ord(ch) > 127 for ch in w) else re.search(rf"\b{w}\b", norm):
                return today + timedelta(days=delta)
    return today


def _extract_channel(norm: str) -> str:
    for ch, words in CHANNELS:
        for w in words:
            if (w in norm) if any(ord(c) > 127 for c in w) else re.search(rf"\b{re.escape(w)}", norm):
                return ch
    return "cash"


def _extract_counterparty(original: str, norm: str) -> str:
    for pat in _PARTY_PATTERNS:
        m = pat.search(norm)
        if m:
            words = [w for w in m.group(1).split() if w not in _NAME_STOP and not re.fullmatch(r"[\d,.]+", w)]
            # trim trailing stop words / amounts
            name = " ".join(words).strip(" ,.")
            if name and not re.fullmatch(r"[\d\s,.]+", name):
                # recover original casing if possible
                idx = original.lower().find(name)
                return original[idx:idx + len(name)] if idx >= 0 else name.title()
    return ""


def parse_entry(text: str, today: date | None = None) -> ParsedEntry:
    today = today or date.today()
    original = bn_to_ascii_digits((text or "").strip())
    norm = normalize(text)
    amount, qty, item = _extract_amount_and_qty(norm)
    direction, dir_kw = detect_direction(norm)
    cat = categorize(norm, direction)
    if direction is None and cat.direction:
        direction = cat.direction
    channel = _extract_channel(norm)
    d = _extract_date(norm, today)
    party = _extract_counterparty(original, norm)

    missing = []
    if amount is None:
        missing.append("amount")
    if direction is None:
        missing.append("direction")
    confidence = (0.45 if amount is not None else 0) + (0.3 if direction else 0) + \
                 (0.25 * cat.confidence / 0.95 if cat.category != "uncategorized" else 0)
    return ParsedEntry(
        amount=round(amount, 2) if amount is not None else None,
        direction=direction, category=cat.category if direction else "uncategorized",
        channel=channel, txn_date=d.isoformat(), counterparty=party, quantity=qty, item=item,
        description=(text or "").strip()[:300], confidence=round(min(confidence, 1.0), 2),
        missing=missing, matched_keyword=cat.keyword or dir_kw,
    )


def parse_date_any(value) -> date | None:
    """Lenient date parser for imports (day-first, as used in Bangladesh)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = bn_to_ascii_digits(str(value)).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y",
                "%d-%b-%y", "%b %d, %Y", "%d %B %Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M",
                "%d-%m-%Y %H:%M", "%d/%m/%Y %I:%M %p", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
