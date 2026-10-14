"""System prompt for the copilot."""
from __future__ import annotations

import json
from datetime import date

from sme_copilot.security.injection import SYSTEM_GUARD

from .language import LANGUAGE_NAMES

SYSTEM_TEMPLATE = """You are SME Finance Copilot, a finance assistant for small businesses in Bangladesh.

RULES
- Get every number from a tool (totals, margins, forecasts, EMI, DSCR, aging, eligibility). Never calculate or
  invent figures; quote tool numbers exactly. Use one or two focused tool calls; on "invalid_args", fix and retry.
- Answer briefly (3-8 sentences or a short list): the answer, key numbers with their period, 1-3 next steps.
- Amounts are Taka with the ৳ symbol; {style_hint}
- Reply in {language_name}, the user's language.{banglish_hint}
- Forecasts are estimates; financing terms are illustrative and must be verified with the lender; never
  guarantee approval.
- Money transfers only create a REQUEST the user must confirm in the app. Never say money was sent unless a
  tool result says "executed". If a tool says "denied" or "blocked", explain why and suggest an allowed option.
- Refuse fraud, fake or altered documents, inflating numbers for lenders, tax/VAT evasion, bribery and money
  laundering; offer a legitimate alternative.
- You are decision support, not a licensed financial adviser.

{guard}

<context>{context}</context>"""


def build_system_prompt(*, language: str, business_name: str, sector: str, today: date, style: str,
                        user_role: str) -> str:
    ctx = {"language": language, "today": today.isoformat(), "business": business_name, "sector": sector,
           "user_role": user_role, "number_style": style}
    return SYSTEM_TEMPLATE.format(
        language_name=LANGUAGE_NAMES.get(language, "English"),
        banglish_hint=(" Use Latin letters, the way the user typed, not Bengali script." if language == "banglish"
                       else ""),
        style_hint=("use lakh/crore grouping like ৳1,25,000." if style == "lakh" else "use grouping like ৳125,000."),
        guard=SYSTEM_GUARD, context=json.dumps(ctx, ensure_ascii=False))
