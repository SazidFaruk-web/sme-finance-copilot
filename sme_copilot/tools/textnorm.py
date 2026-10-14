"""Text normalisation for Bangla / English / Banglish input."""
from __future__ import annotations

import re
import unicodedata

BN_DIGITS = "০১২৩৪৫৬৭৮৯"
_BN_TO_ASCII = str.maketrans(BN_DIGITS, "0123456789")
_ASCII_TO_BN = str.maketrans("0123456789", BN_DIGITS)

_BN_RANGE = re.compile(r"[ঀ-৿]")
_WS = re.compile(r"\s+")


def bn_to_ascii_digits(text: str) -> str:
    return text.translate(_BN_TO_ASCII)


def ascii_to_bn_digits(text: str) -> str:
    return text.translate(_ASCII_TO_BN)


def normalize(text: str) -> str:
    """NFC, Bangla digits -> ASCII, lowercase Latin, collapse whitespace."""
    text = unicodedata.normalize("NFC", text or "")
    text = bn_to_ascii_digits(text)
    return _WS.sub(" ", text.lower()).strip()


def bangla_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha() or _BN_RANGE.match(c)]
    if not letters:
        return 0.0
    return sum(1 for c in letters if _BN_RANGE.match(c)) / len(letters)


def has_bangla(text: str) -> bool:
    return bool(_BN_RANGE.search(text or ""))


def contains_keyword(norm_text: str, keyword: str) -> bool:
    """Word-boundary match for Latin keywords; substring match for Bangla (suffix-rich script)."""
    kw = normalize(keyword)
    if not kw:
        return False
    if has_bangla(kw):
        return kw in norm_text
    return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", norm_text) is not None
