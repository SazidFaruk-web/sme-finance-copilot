"""Detect the user's language so the copilot replies in kind: English, Bangla, or Banglish."""
from __future__ import annotations

import re

from sme_copilot.tools.textnorm import bangla_ratio

BANGLISH_MARKERS = {
    "ami", "amar", "amake", "apni", "apnar", "tumi", "tomar", "koto", "kemon", "dokan", "bikri", "khoroch",
    "lav", "labh", "mash", "mas", "hobe", "ache", "achhe", "ase", "ki", "keno", "korbo", "korte", "korun", "koren",
    "dilam", "pelam", "kinlam", "bechlam", "theke", "bolo", "bolun", "janao", "jodi", "tahole", "bhara", "beton",
    "kisti", "rin", "baki", "pawna", "dena", "hisab", "ei", "gato", "gotokal", "aj", "porer", "agami", "shob",
    "sob", "kom", "beshi", "lagbe", "dorkar", "parbo", "chai", "den", "dekhao", "dekhan", "hoyeche", "hoise",
    "nai", "nei", "kivabe", "kothay", "kar", "kake", "dao", "pathao", "taka", "byabsa", "byabsha", "bebsa",
    "sathe", "jonno", "niye", "korlam", "hoye", "jabe", "thakbe", "pabo", "kotodin", "cholbe", "kemne",
}


def detect_language(text: str) -> str:
    """'bn' (Bangla script), 'banglish' (Bangla in Latin script) or 'en'."""
    if not text:
        return "en"
    if bangla_ratio(text) >= 0.3:
        return "bn"
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return "en"
    hits = sum(1 for w in words if w in BANGLISH_MARKERS)
    # "taka" alone shows up in English entries ("6000 taka"), so it never decides on its own.
    strong = hits - (1 if "taka" in words else 0)
    if strong >= 2 or (strong >= 1 and hits / len(words) >= 0.25):
        return "banglish"
    return "en"


LANGUAGE_NAMES = {"en": "English", "bn": "Bangla (Bengali script)", "banglish": "Banglish (Bangla written in "
                                                                              "Latin letters)"}
