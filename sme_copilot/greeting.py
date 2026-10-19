"""A fresh one-line greeting for the AI Assistant tab, written by the local model each time the app opens.

Any failure (rules-only profile, model offline, timeout, odd output) returns None and the UI keeps its fixed greeting.
"""
from __future__ import annotations

import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from sme_copilot.llm_providers.base import Message

log = logging.getLogger(__name__)

TIMEOUT_S = 20.0
MAX_CHARS = 260
LANGS = {"en": "English", "bn": "Bangla (Bengali script)", "zh": "Simplified Chinese"}
TONES = ["warm and upbeat", "calm and friendly", "short and cheerful", "relaxed and encouraging",
         "energetic", "gentle and welcoming", "casual, like a helpful friend"]
OPENERS = ["Hey", "Hi", "Hello", "Welcome back", "Good to see you", "Nice to have you here", "Hi there", "Great to see you"]
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="greeting")


def _prompt(first_name: str, language: str, tone: str, simple: bool, opener: str) -> list[Message]:
    offer = ("It can explain their records and suggest a small next step." if simple else
             "It can answer questions about sales, costs, cash flow and loans, record entries, "
             "draft reminders and prepare loan reports.")
    system = ("You write the first message shown in the chat tab of a money app for small shop owners in Bangladesh. "
              f"Write ONE fresh greeting of 1-2 short sentences in {LANGS[language]}, tone: {tone}, starting with something like \"{opener}\" (translated if needed). "
              "It must say the assistant is their AI Assistant for business money and mention what it can do: "
              f"{offer} Do not use a religious greeting. Do not use emojis, quotes, markdown or lists. "
              "Do not promise anything that is not listed. Output only the greeting text.")
    who = f"The owner's first name is {first_name}. You may use it once." if first_name else "Do not use a name."
    return [Message("system", system), Message("user", who + f" Variation seed: {random.randint(1000, 9999)}.")]


def clean(text: str) -> str | None:
    t = re.sub(r"<[^>]*>", "", text or "")
    t = re.sub(r"[*_`#>]+", "", t).strip().strip("\"'“”").strip()
    t = " ".join(t.split())
    if len(t) < 20 or re.search(r"https?://|www\.|assalam", t, re.I):
        return None
    if len(t) > MAX_CHARS:
        cut = t[:MAX_CHARS]
        t = cut[:max(cut.rfind(". "), cut.rfind("। "))].strip() if (". " in cut or "। " in cut) else None
        if not t or len(t) < 20:
            return None
    return t


def make_greeting(first_name: str = "", language: str = "en", profile: str | None = None, simple: bool = False,
                  provider: Any = None, timeout: float = TIMEOUT_S) -> str | None:
    language = language if language in LANGS else "en"
    first = re.sub(r"[^\w .'-]", "", first_name or "").strip().split(" ")[0][:20]
    try:
        if provider is None:
            from sme_copilot.llm_providers.registry import get_registry
            reg = get_registry()
            provider = reg.get(profile if profile in reg.profiles else reg.default_profile)
        if getattr(provider, "adapter", "") == "rules":  # offline rules engine cannot write text
            return None
        msgs = _prompt(first, language, random.choice(TONES), simple, random.choice(OPENERS))
        resp = _pool.submit(lambda: provider.chat(msgs, temperature=0.95, max_tokens=120)).result(timeout=timeout)
        return clean(resp.content)
    except FutureTimeout:
        log.info("greeting timed out after %.0fs; using the fixed one", timeout)
    except Exception as e:  # noqa: BLE001 - any provider failure -> fixed greeting
        log.info("greeting failed (%s); using the fixed one", e)
    return None
