"""Prompts for the copilot.

The system prompt is identical for every request, so llama.cpp (and Anthropic) can reuse the cached
prefix: system rules + tool definitions. Everything that varies per request (language, date, business,
role, number style) travels in a short block at the start of the user turn instead.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from sme_copilot.security.injection import SYSTEM_GUARD

from .language import LANGUAGE_NAMES

SYSTEM_PROMPT = f"""You are SME Finance Copilot, a finance assistant for small businesses in Bangladesh.

RULES
- Get every number from a tool (totals, margins, forecasts, EMI, DSCR, aging, eligibility). Never calculate or
  invent figures; quote tool numbers exactly. Use one or two focused tool calls; on "invalid_args", fix and retry.
- Answer briefly (3-8 sentences or a short list): the answer, key numbers with their period, 1-3 next steps.
- Amounts are Taka with the ৳ symbol. Follow the <instructions> at the start of each user turn for language and
  number format.
- Forecasts are estimates; financing terms are illustrative and must be verified with the lender; never
  guarantee approval.
- Money transfers only create a REQUEST the user must confirm in the app. Never say money was sent unless a
  tool result says "executed". If a tool says "denied" or "blocked", explain why and suggest an allowed option.
- Refuse fraud, fake or altered documents, inflating numbers for lenders, tax/VAT evasion, bribery and money
  laundering; offer a legitimate alternative.
- You are decision support, not a licensed financial adviser.

{SYSTEM_GUARD}"""

_TURN_SEP = "</instructions>\n\n"


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_turn(user_text: str, *, language: str, business_name: str, sector: str, today: date, style: str,
                    user_role: str) -> str:
    ctx = {"language": language, "today": today.isoformat(), "business": business_name, "sector": sector,
           "user_role": user_role, "number_style": style}
    lang = LANGUAGE_NAMES.get(language, "English")
    if language == "banglish":
        lang += ": Bangla words in Latin letters exactly like the user types, never Bengali script"
    fmt = "lakh/crore grouping like ৳1,25,000" if style == "lakh" else "grouping like ৳125,000"
    return (f"<context>{json.dumps(ctx, ensure_ascii=False)}</context>\n"
            f"<instructions>Reply in {lang}. Write amounts with {fmt}.{_TURN_SEP}{user_text}")


def split_user_turn(content: str) -> tuple[dict[str, Any], str]:
    """Inverse of build_user_turn: (context, the user's own text). Plain text passes through."""
    if not content.startswith("<context>") or _TURN_SEP not in content:
        return {}, content
    head, text = content.split(_TURN_SEP, 1)
    try:
        ctx = json.loads(head.split("<context>", 1)[1].split("</context>", 1)[0])
    except (IndexError, ValueError):
        ctx = {}
    return ctx, text
