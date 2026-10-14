"""BDT amount parsing and formatting (international or lakh/crore grouping)."""
from __future__ import annotations

import math
import re

from .textnorm import ascii_to_bn_digits, bn_to_ascii_digits

TAKA = "৳"

_CURRENCY_NOISE = re.compile(r"(?i)(৳|bdt|tk\.?|taka|টাকা)")


def parse_amount(value) -> float | None:
    """Parse '৳1,20,000.50', 'Tk 500', '(2,000)', '১৫০০', 1500 -> float. None if not a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    s = bn_to_ascii_digits(str(value)).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = _CURRENCY_NOISE.sub("", s)
    s = s.replace(",", "").replace("(", "").replace(")", "").replace("-", "").strip()
    if s.lower().endswith(("dr", "cr")):
        s = s[:-2].strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def group_lakh(int_part: str) -> str:
    """'12345678' -> '1,23,45,678' (South Asian grouping)."""
    if len(int_part) <= 3:
        return int_part
    head, tail = int_part[:-3], int_part[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def format_bdt(amount: float | None, *, style: str = "lakh", decimals: int = 0, symbol: bool = True,
               bangla_digits: bool = False) -> str:
    if amount is None:
        return "-"
    neg = amount < 0
    amount = round(abs(amount), decimals)
    int_part, _, frac = f"{amount:.{decimals}f}".partition(".")
    grouped = group_lakh(int_part) if style == "lakh" else f"{int(int_part):,}"
    s = grouped + (f".{frac}" if decimals else "")
    if bangla_digits:
        s = ascii_to_bn_digits(s)
    s = (TAKA if symbol else "") + s
    return "-" + s if neg else s


def words_lakh(amount: float) -> str:
    """Human scale: 1500000 -> '15 lakh', 25000000 -> '2.5 crore'."""
    a = abs(amount)
    if a >= 1e7:
        return f"{a / 1e7:.2f}".rstrip("0").rstrip(".") + " crore"
    if a >= 1e5:
        return f"{a / 1e5:.2f}".rstrip("0").rstrip(".") + " lakh"
    return f"{a:,.0f}"
