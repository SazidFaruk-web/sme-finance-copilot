"""Offline rule-based intent engine (the "rules-offline" model).

``plan``: keyword/regex intent detection in English, Bangla and Banglish -> tool calls.
``compose``: templated answers in the user's language, built only from tool results.

It deliberately mirrors what an LLM does in the agent loop, so the whole product (and its
security controls) works with no model, and gives the benchmark a deterministic baseline.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from sme_copilot.llm_providers.base import ToolCall, ToolSpec
from sme_copilot.tools.money import format_bdt
from sme_copilot.tools.nl_entry import _extract_amount_and_qty, parse_entry
from sme_copilot.tools.textnorm import ascii_to_bn_digits, normalize

# ----------------------------------------------------------------------------- vocabulary
CAT_NAMES = {
    "bn": {"sales": "বিক্রি", "inventory": "মাল/কাঁচামাল কেনা", "rent": "ভাড়া", "salary": "বেতন",
           "utilities": "বিদ্যুৎ-গ্যাস-ইন্টারনেট", "transport": "পরিবহন", "loan_repayment": "ঋণের কিস্তি",
           "packaging": "প্যাকেজিং", "marketing": "বিজ্ঞাপন", "mobile_fees": "মোবাইল/ব্যাংক চার্জ",
           "maintenance": "মেরামত", "tax_vat": "কর/ভ্যাট", "equipment": "যন্ত্রপাতি", "owner_drawings": "নিজের খরচ",
           "food_entertainment": "চা-নাস্তা", "misc_expense": "অন্যান্য", "other_income": "অন্যান্য আয়",
           "loan_received": "ঋণ প্রাপ্তি", "owner_capital": "মালিকের মূলধন", "uncategorized": "অশ্রেণীকৃত"},
    "banglish": {"sales": "bikri", "inventory": "mal kena", "rent": "bhara", "salary": "beton",
                 "utilities": "bijli-gas-internet", "transport": "poribohon", "loan_repayment": "loan er kisti",
                 "packaging": "packaging", "marketing": "marketing", "mobile_fees": "charge",
                 "maintenance": "meramot", "tax_vat": "tax/vat", "equipment": "jontropati", "owner_drawings": "nijer khoroch",
                 "food_entertainment": "cha-nasta", "misc_expense": "onnanno", "other_income": "onnanno ay",
                 "loan_received": "loan prapti", "owner_capital": "puji", "uncategorized": "uncategorized"},
}

QUESTION_RX = re.compile(r"\?|^(how|what|why|when|which|who|can|should|is|are|do|does|will|show|tell|give|list)\b|"
                         r"\b(koto|ki|kii|keno|kivabe|kothay|kemon|kobe|ache ki)\b|(কত|কী|কি|কেন|কিভাবে|কোথায়|কেমন|কবে)")
PAST_ENTRY_RX = re.compile(r"\b(sold|paid|bought|received|got|spent|purchased|collected|deposited|dilam|diyechi|"
                           r"pelam|peyechi|kinlam|bechlam|korlam|bikri korlam|khoroch korlam)\b|"
                           r"(দিলাম|দিয়েছি|পেলাম|পেয়েছি|কিনলাম|বেচলাম|বিক্রি করলাম|খরচ করলাম|বিক্রি হলো)")


def _has(text: str, words: list[str]) -> bool:
    for w in words:
        if any(ord(c) > 127 for c in w):
            if w in text:
                return True
        elif re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text):
            return True
    return False


def detect_period(t: str, default: str) -> str:
    if _has(t, ["last month", "previous month", "gato mash", "goto mash", "gato mas", "গত মাস", "গত মাসে",
                "last maser", "ager mash"]):
        return "last_month"
    if _has(t, ["this month", "ei mash", "ei mas", "এই মাস", "এই মাসে", "current month"]):
        return "this_month"
    m = re.search(r"(?:last|past|gato|goto|গত)\s*(\d{1,2})\s*(?:months?|mash|mas|মাস)", t)
    if m:
        n = int(m.group(1))
        return {1: "last_month", 3: "last_3_months", 6: "last_6_months", 12: "last_12_months"}.get(
            n, "last_6_months" if n <= 6 else "last_12_months")
    if _has(t, ["this year", "ytd", "ei bochor", "এই বছর", "year to date"]):
        return "ytd"
    if _has(t, ["last year", "12 months", "1 year", "gato bochor", "গত বছর", "one year"]):
        return "last_12_months"
    if _has(t, ["fiscal year", "this fy", "orthobochor", "অর্থবছর"]):
        return "fiscal_ytd"
    if _has(t, ["last 30 days", "30 days", "30 din"]):
        return "last_30_days"
    if _has(t, ["quarter", "3 months", "tin mash", "তিন মাস"]):
        return "last_3_months"
    return default


def detect_horizon(t: str) -> int:
    m = re.search(r"(\d{2,3})\s*(?:days?|din|দিন)", t)
    if m and int(m.group(1)) in (30, 60, 90):
        return int(m.group(1))
    m = re.search(r"(\d)\s*(?:months?|mash|mas|মাস)", t)
    if m:
        return min(90, max(30, int(m.group(1)) * 30))
    return 90


def _amount(t: str) -> float | None:
    amt, _, _ = _extract_amount_and_qty(t)
    return amt


def _pct(t: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent|parcent|shotangsho|শতাংশ)", t)
    return float(m.group(1)) if m else None


def _days(t: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*(?:days?|din|দিন)", t)
    return int(m.group(1)) if m else None


def _name_after(t: str, original: str, words: tuple[str, ...]) -> str:
    """Pick a proper name after 'to'/'from' or before 'ke'/'কে' using the original casing."""
    for w in words:
        m = re.search(rf"\b{w}\s+([A-Za-z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){{0,3}})", original)
        if m:
            name = re.split(r"\s+(?:for|about|regarding|via|by|on|taka|tk)\b", m.group(1))[0]
            if name.lower() not in ("me", "my", "the", "a", "an", "all", "customers", "customer", "supplier"):
                return name.strip(" .,")
    m = re.search(r"([A-Za-z][\w&.'-]*(?:\s+[A-Za-z][\w&.'-]*){0,2})\s+(?:ke|k)\b", original)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\S+)\s*কে", original)
    if m:
        return m.group(1)
    return ""


def parse_scenarios(t: str, original: str) -> list[dict[str, Any]]:
    """What-if text -> scenario objects (schema in forecasting/whatif.py)."""
    scen: list[dict[str, Any]] = []
    days = _days(t)
    if days and _has(t, ["late", "delay", "deri", "দেরি", "pays", "pay", "payment", "dey", "dibe"]):
        cust = "biggest" if _has(t, ["biggest", "largest", "main", "top", "boro", "sobcheye boro", "সবচেয়ে বড়"]) else \
            (_name_after(t, original, ("customer",)) or "biggest")
        scen.append({"kind": "delay_receivable", "customer": cust, "days": days})
    if _has(t, ["loan", "rin", "ঋণ", "লোন", "borrow"]):
        amt = _amount(t)
        if amt:
            sc: dict[str, Any] = {"kind": "loan", "amount": amt}
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
            if m:
                sc["annual_rate_pct"] = float(m.group(1))
            m = re.search(r"(\d{1,3})\s*(?:months?|mash|mas|মাস)", t)
            if m:
                sc["months"] = int(m.group(1))
            m = re.search(r"(\d{1,2})\s*(?:years?|bochor|বছর)", t)
            if m:
                sc["months"] = int(m.group(1)) * 12
            scen.append(sc)
    pct = _pct(t)
    if pct is not None and _has(t, ["sales", "revenue", "bikri", "বিক্রি", "income", "orders"]) and \
            not any(s["kind"] == "loan" for s in scen):
        down = _has(t, ["drop", "fall", "fell", "decrease", "down", "kome", "kombe", "kom", "কমে", "কমলে", "lower", "less"])
        scen.append({"kind": "revenue_change", "pct": -pct if down else pct})
    if _has(t, ["hire", "new staff", "new worker", "notun staff", "নতুন কর্মী", "salary increase", "beton barai"]):
        amt = _amount(t)
        if amt:
            scen.append({"kind": "expense_change", "category": "salary", "monthly_amount": amt})
    if _has(t, ["rent"]) and (pct is not None or _amount(t)) and not scen:
        if pct is not None:
            scen.append({"kind": "expense_change", "category": "rent", "pct": pct})
        else:
            scen.append({"kind": "expense_change", "category": "rent", "monthly_amount": _amount(t)})
    if _has(t, ["buy", "machine", "equipment", "kini", "kinbo", "কিনি", "কিনলে"]) and not scen:
        amt = _amount(t)
        if amt:
            scen.append({"kind": "one_off", "amount": amt, "direction": "out", "description": "one-off purchase"})
    return scen


def parse_due_date(t: str, today: date) -> str | None:
    """'tomorrow', 'in 5 days', 'on 15th', '15 tarikh', '20/10/2026' -> ISO date (or None)."""
    from datetime import timedelta

    from sme_copilot.tools.analysis import add_months
    from sme_copilot.tools.nl_entry import _DATE_PATTERNS
    for pat, kind in _DATE_PATTERNS:
        m = pat.search(t)
        if m:
            a, b, c = (int(x) for x in m.groups())
            try:
                return (date(c, b, a) if kind == "dmy" else date(a, b, c)).isoformat()
            except ValueError:
                pass
    if _has(t, ["tomorrow", "agamikal", "আগামীকাল"]):
        return (today + timedelta(days=1)).isoformat()
    m = re.search(r"in\s+(\d{1,3})\s*days?|(\d{1,3})\s*din pore|(\d{1,3})\s*দিন পর", t)
    if m:
        return (today + timedelta(days=int(next(g for g in m.groups() if g)))).isoformat()
    m = re.search(r"(?:on|by)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b|(\d{1,2})\s*(?:tarikh|তারিখ)", t)
    if m:
        day = int(next(g for g in m.groups() if g))
        if 1 <= day <= 28:
            d = today.replace(day=day)
            if d <= today:
                d = add_months(d, 1)
            return d.isoformat()
    return None


# ----------------------------------------------------------------------------- planning
Builder = Callable[[str, str, dict[str, Any]], dict[str, Any] | None]


def _intents() -> list[tuple[str, list[str], Builder]]:
    def period_args(default):
        return lambda t, o, c: {"period": detect_period(t, default)}

    def transfer(t, o, c):
        amt = _amount(t)
        if not amt or QUESTION_RX.search(t):
            return None
        rec = _name_after(t, o, ("to",))
        return {"recipient_name": rec or "unknown recipient", "amount": amt,
                "purpose": "requested via chat"}

    def reminder(t, o, c):
        name = _name_after(t, o, ("remind", "to", "for", "customer"))
        return {"counterparty": name} if name else {"counterparty": ""}

    def followup(t, o, c):
        name = _name_after(t, o, ("to", "for", "customer"))
        tone = "firm" if _has(t, ["firm", "strict", "final", "kora", "কড়া"]) else "polite"
        lang = c.get("language", "en")
        return {"counterparty": name, "tone": tone, "language": "bn" if lang == "bn" else "en"}

    def what_if(t, o, c):
        sc = parse_scenarios(t, o)
        return {"scenarios": sc, "horizon_days": 90} if sc else None

    def financing(t, o, c):
        amt = _amount(t)
        args: dict[str, Any] = {}
        if amt and amt >= 10_000:
            args["amount"] = amt
        m = re.search(r"(\d{1,3})\s*(?:months?|mash|mas|মাস)", t)
        if m:
            args["tenure_months"] = int(m.group(1))
        if _has(t, ["machine", "equipment", "machinery"]):
            args["purpose"] = "equipment"
        elif _has(t, ["stock", "inventory", "working capital", "mal", "eid"]):
            args["purpose"] = "working_capital"
        return args

    def emi(t, o, c):
        amt = _amount(t)
        rate = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
        months = re.search(r"(\d{1,3})\s*(?:months?|mash|mas|মাস)", t)
        years = re.search(r"(\d{1,2})\s*(?:years?|bochor|বছর)", t)
        if not (amt and rate):
            return None
        n = int(months.group(1)) if months else (int(years.group(1)) * 12 if years else 12)
        return {"principal": amt, "annual_rate_pct": float(rate.group(1)), "months": n,
                "method": "flat" if _has(t, ["flat"]) else "reducing"}

    def schedule(t, o, c):
        today = date.fromisoformat(c.get("today", date.today().isoformat()))
        return {"title": o.strip()[:120], "due_date": parse_due_date(t, today)}

    def entry(t, o, c):
        if QUESTION_RX.search(t) or not PAST_ENTRY_RX.search(t):
            return None
        e = parse_entry(o, date.fromisoformat(c.get("today", date.today().isoformat())))
        if e.amount is None or e.direction is None or e.confidence < 0.7:
            return None
        return {"text": o.strip()[:300]}

    def compliance(t, o, c):
        for topic, words in [("vat", ["vat", "mushak", "ভ্যাট", "মূসক"]), ("tin", ["tin", "e-tin", "income tax", "return"]),
                             ("trade_license", ["trade license", "trade licence", "ট্রেড লাইসেন্স"]),
                             ("kyc_aml", ["kyc", "aml", "money laundering"])]:
            if _has(t, words):
                return {"topic": topic}
        return None

    return [
        ("run_what_if", ["what if", "what happens if", "suppose", "jodi", "যদি", "dhoro", "ধরো", "ধরুন", "scenario"], what_if),
        ("add_transaction", [], entry),
        ("schedule_alert", ["alert me", "notify me", "set an alert", "remind me", "amake mone", "আমাকে মনে"], schedule),
        ("create_payment_reminder", ["reminder", "remind", "tagada", "তাগাদা", "মনে করিয়ে"], reminder),
        ("draft_invoice_followup", ["draft", "follow up", "follow-up", "followup", "message to", "letter", "chithi",
                                    "চিঠি", "বার্তা", "write to", "sms likh"], followup),
        ("sandbox_transfer", ["transfer", "send money", "send", "pathao", "pathan", "পাঠাও", "পাঠান", "ট্রান্সফার",
                              "pay "], transfer),
        ("generate_loan_report", ["loan report", "readiness report", "pdf", "report for the bank", "bank report",
                                  "loan application report"], lambda t, o, c: {"amount": _amount(t)} if _amount(t) else {}),
        ("prepare_loan_checklist", ["checklist", "documents needed", "documents", "what papers", "kagoj", "কাগজ",
                                    "kagojpotro", "কাগজপত্র"], lambda t, o, c: {}),
        ("loan_readiness_score", ["readiness", "ready for a loan", "loan ready", "credit score", "score", "eligible",
                                  "eligibility", "joggo", "যোগ্য", "prostut", "প্রস্তুত"], lambda t, o, c: {}),
        ("calculate_loan", ["emi", "installment", "instalment", "kisti koto", "কিস্তি কত", "monthly payment"], emi),
        ("match_financing", ["loan", "loans", "finance", "financing", "financing options", "lenders", "credit", "rin", "ঋণ", "লোন", "borrow", "funding",
                             "capital", "dhar", "ধার", "lender"], financing),
        ("forecast_cash_flow", ["forecast", "cash flow", "cashflow", "next 30", "next 60", "next 90", "runway",
                                "run out", "kotodin", "কতদিন", "নগদ প্রবাহ", "agami", "আগামী", "shortfall",
                                "projection", "cholbe", "চলবে"], lambda t, o, c: {"horizon_days": detect_horizon(t)}),
        ("get_digest", ["alert", "alerts", "attention", "digest", "to do", "todo", "what should i do", "ki korte hobe",
                        "কী করতে হবে", "সতর্ক", "warning", "this week", "important", "priority", "agenda"],
         lambda t, o, c: {}),
        ("compliance_info", ["vat", "mushak", "tin", "e-tin", "trade license", "trade licence", "kyc", "aml", "nbr",
                             "ভ্যাট", "মূসক", "ট্রেড লাইসেন্স", "tax return"], compliance),
        ("get_aging:payable", ["payable", "payables", "i owe", "we owe", "supplier due", "dena", "দেনা",
                               "supplier ke dite", "bills to pay"], lambda t, o, c: {"kind": "payable"}),
        ("get_aging", ["receivable", "receivables", "owe me", "owes me", "owes", "overdue", "unpaid", "due from",
                       "baki", "বাকি", "pawna", "পাওনা", "collect", "outstanding"], lambda t, o, c: {"kind": "receivable"}),
        ("get_break_even", ["break even", "break-even", "breakeven", "lav loss soman", "লাভ-ক্ষতি সমান",
                            "minimum sales"], lambda t, o, c: {"months": 3}),
        ("explain_change", ["why", "keno", "কেন", "what changed", "drop", "dropped", "fell", "decrease", "decreased",
                            "komlo", "কমল", "komeche", "কমেছে", "barlo", "বাড়ল", "increased", "went down", "went up"],
         period_args("last_month")),
        ("get_seasonality", ["season", "seasonal", "seasonality", "eid", "festival", "boishakh", "puja", "মৌসুম",
                             "ঈদ", "utsob", "উৎসব"], lambda t, o, c: {}),
        ("search_transactions:flagged", ["unusual", "anomaly", "anomalies", "suspicious", "duplicate", "duplicates",
                                         "odd", "strange", "oshabhabik", "অস্বাভাবিক"],
         lambda t, o, c: {"flagged_only": True, "period": "last_12_months"}),
        ("get_cost_drivers", ["cost", "costs", "expense", "expenses", "spending", "spend", "khoroch", "খরচ", "ব্যয়"],
         period_args("last_month")),
        ("get_profitability", ["margin", "profit", "lav", "labh", "লাভ", "মুনাফা", "profitable", "gross", "net"],
         period_args("last_3_months")),
        ("get_cash_position", ["balance", "cash in hand", "how much cash", "koto taka ache", "কত টাকা আছে",
                               "hate koto", "bank balance"], lambda t, o, c: {}),
        ("overview", ["summary", "overview", "how am i doing", "how is my business", "business kemon", "byabsa kemon",
                      "ব্যবসা কেমন", "sales", "income", "bikri", "বিক্রি", "revenue", "hisab", "হিসাব", "report",
                      "performance", "kemon cholche"], period_args("last_3_months")),
    ]


HELP = {
    "en": ("I can analyse your sales and costs, forecast cash flow, run what-if scenarios, match financing options, "
           "and draft reminders or reports. Try: \"How did I do last month?\", \"What if my biggest customer pays "
           "20 days late?\", or \"Which loans fit me?\""),
    "bn": ("আমি আপনার বিক্রি-খরচ বিশ্লেষণ, নগদ প্রবাহের পূর্বাভাস, 'যদি' পরিস্থিতি যাচাই, ঋণের বিকল্প খোঁজা এবং "
           "তাগাদা বা রিপোর্ট তৈরি করতে পারি। যেমন লিখুন: \"গত মাসে লাভ কত?\" বা \"আমার জন্য কোন ঋণ ভালো?\""),
    "banglish": ("Ami apnar bikri-khoroch analysis, cash flow forecast, 'jodi' scenario, loan option khuja, ar "
                 "tagada ba report banate pari. Jemon likhun: \"gato mash e lav koto?\" ba \"amar jonno kon loan "
                 "bhalo?\""),
}


class RuleIntentEngine:
    def plan(self, user_text: str, tools: list[ToolSpec], context: dict[str, Any]) -> list[ToolCall] | str:
        names = {t.name for t in tools}
        t = normalize(user_text)
        lang = context.get("language", "en")
        for intent, words, builder in _intents():
            if words and not _has(t, words):
                continue
            tool_name = intent.split(":")[0]
            if intent == "overview":
                calls = [c for c in (("get_financial_summary", builder(t, user_text, context)),
                                     ("get_profitability", builder(t, user_text, context))) if c[0] in names]
                if calls:
                    return [ToolCall(n, a) for n, a in calls]
                continue
            if tool_name not in names:
                continue
            args = builder(t, user_text, context)
            if args is None:
                continue
            return [ToolCall(tool_name, args)]
        return HELP.get(lang, HELP["en"])

    def compose(self, user_text: str, tool_results: list[tuple[str, dict[str, Any]]], context: dict[str, Any]) -> str:
        lang = context.get("language", "en")
        style = context.get("number_style", "lakh")
        if not tool_results:
            return HELP.get(lang, HELP["en"])
        parts = []
        for name, payload in tool_results:
            status = payload.get("status")
            if status in ("denied", "blocked"):
                parts.append(_denied(lang, payload.get("message", "")))
                continue
            if status == "pending_confirmation":
                parts.append(_pending(lang, payload))
                continue
            if status != "ok":
                parts.append(_error(lang, payload.get("message", "")))
                continue
            res = payload.get("result") or {}
            fn = COMPOSERS.get(name, _generic)
            parts.append(fn(res, Fmt(lang, style)))
        return "\n\n".join(p for p in parts if p)


# ----------------------------------------------------------------------------- composing
class Fmt:
    def __init__(self, lang: str, style: str):
        self.lang, self.style = lang, style

    def m(self, v: float | None) -> str:
        return format_bdt(v, style=self.style, bangla_digits=self.lang == "bn")

    def n(self, v: Any) -> str:
        s = f"{v:g}" if isinstance(v, float) else str(v)
        return ascii_to_bn_digits(s) if self.lang == "bn" else s

    def cat(self, c: str) -> str:
        return CAT_NAMES.get(self.lang, {}).get(c, c.replace("_", " "))

    def pick(self, en: str, bn: str, bl: str) -> str:
        return {"en": en, "bn": bn, "banglish": bl}.get(self.lang, en)


def _denied(lang: str, msg: str) -> str:
    return {"bn": f"এই কাজটি অনুমোদিত নয়: {msg}", "banglish": f"Ei kaj ta allowed na: {msg}"}.get(
        lang, f"I can't do that: {msg}")


def _error(lang: str, msg: str) -> str:
    return {"bn": f"কাজটি সম্পন্ন করা যায়নি: {msg}", "banglish": f"Kaj ta kora jayni: {msg}"}.get(
        lang, f"That didn't work: {msg}")


def _pending(lang: str, p: dict[str, Any]) -> str:
    r = p.get("result") or {}
    s = r.get("summary", "")
    return {"bn": f"অনুরোধ তৈরি হয়েছে, কিন্তু টাকা এখনো পাঠানো হয়নি: {s}। অ্যাপে পরিমাণ ও প্রাপক যাচাই করে নিশ্চিত করুন।",
            "banglish": f"Request toiri hoyeche, kintu taka ekhono pathano hoyni: {s}. App e amount ar prapok "
                        f"check kore confirm korun."}.get(
        lang, f"I've prepared this request but NOTHING has been sent yet: {s}. Please review the amount and "
              f"recipient and confirm it in the app.")


def _generic(r: dict[str, Any], f: Fmt) -> str:
    tr = r.get("trace") or {}
    steps = tr.get("steps") or []
    if not steps:
        return f.pick("Done.", "সম্পন্ন হয়েছে।", "Hoye geche.")
    lines = [f"- {s['label']}: {f.m(s['value']) if isinstance(s['value'], (int, float)) and abs(s['value']) >= 100 else f.n(s['value'])}"
             for s in steps[:8]]
    return "\n".join(lines)


def c_summary(r, f: Fmt) -> str:
    top = (r.get("expense_by_category") or [{}])[0]
    topc = f"{f.cat(top['category'])} ({f.n(top['share_pct'])}%)" if top else "-"
    return f.pick(
        f"For {r['period']}: income {f.m(r['total_income'])}, expenses {f.m(r['total_expense'])}, net cash flow "
        f"{f.m(r['net_cash_flow'])}. Biggest cost: {topc}. Based on {r['transaction_count']} transactions.",
        f"{r['period']} সময়ে: মোট আয় {f.m(r['total_income'])}, মোট খরচ {f.m(r['total_expense'])}, নিট নগদ প্রবাহ "
        f"{f.m(r['net_cash_flow'])}। সবচেয়ে বড় খরচ: {topc}। মোট {f.n(r['transaction_count'])}টি লেনদেনের ভিত্তিতে।",
        f"{r['period']} e: mot ay {f.m(r['total_income'])}, mot khoroch {f.m(r['total_expense'])}, net cash flow "
        f"{f.m(r['net_cash_flow'])}. Sobcheye boro khoroch: {topc}. {r['transaction_count']} ta lenden theke.")


def c_profit(r, f: Fmt) -> str:
    gm = f.n(r["gross_margin_pct"]) + "%" if r.get("gross_margin_pct") is not None else "-"
    nm = f.n(r["net_margin_pct"]) + "%" if r.get("net_margin_pct") is not None else "-"
    return f.pick(
        f"Profitability ({r['period']}): revenue {f.m(r['revenue'])}, cost of goods {f.m(r['cogs'])}, gross profit "
        f"{f.m(r['gross_profit'])} (gross margin {gm}). After operating costs, operating profit is "
        f"{f.m(r['operating_profit'])} (net operating margin {nm}). Loan repayments and owner drawings are shown "
        f"separately, not deducted.",
        f"লাভ-ক্ষতি ({r['period']}): বিক্রি {f.m(r['revenue'])}, মালের খরচ {f.m(r['cogs'])}, মোট লাভ "
        f"{f.m(r['gross_profit'])} (গ্রস মার্জিন {gm})। পরিচালন খরচ বাদে লাভ {f.m(r['operating_profit'])} "
        f"(নিট মার্জিন {nm})।",
        f"Lav-khoti ({r['period']}): bikri {f.m(r['revenue'])}, maler khoroch {f.m(r['cogs'])}, gross lav "
        f"{f.m(r['gross_profit'])} (gross margin {gm}). Shob khoroch bad e operating lav {f.m(r['operating_profit'])} "
        f"(net margin {nm}).")


def c_break_even(r, f: Fmt) -> str:
    if r.get("break_even_monthly_revenue") is None:
        return f.pick("Break-even can't be computed: variable costs are at or above revenue (or there is no revenue).",
                      "ব্রেক-ইভেন হিসাব করা যাচ্ছে না: পরিবর্তনশীল খরচ বিক্রির সমান বা বেশি।",
                      "Break-even hisab kora jacche na: variable khoroch bikrir soman ba beshi.")
    return f.pick(
        f"You need about {f.m(r['break_even_monthly_revenue'])} in sales per month (~{f.m(r['break_even_daily_revenue'])}"
        f"/day) to cover fixed costs of {f.m(r['avg_monthly_fixed_costs'])}. Your recent average is "
        f"{f.m(r['avg_monthly_revenue'])}, a margin of safety of {f.n(r['margin_of_safety_pct'])}%.",
        f"স্থির খরচ {f.m(r['avg_monthly_fixed_costs'])} তুলতে মাসে প্রায় {f.m(r['break_even_monthly_revenue'])} বিক্রি "
        f"দরকার। আপনার গড় বিক্রি {f.m(r['avg_monthly_revenue'])}, নিরাপত্তা মার্জিন {f.n(r['margin_of_safety_pct'])}%।",
        f"Fixed khoroch {f.m(r['avg_monthly_fixed_costs'])} tulte mashe prai {f.m(r['break_even_monthly_revenue'])} "
        f"bikri lagbe. Apnar gor bikri {f.m(r['avg_monthly_revenue'])}, safety margin {f.n(r['margin_of_safety_pct'])}%.")


def c_aging(r, f: Fmt) -> str:
    who = ", ".join([f"{c['counterparty']} {f.m(c['overdue'])}" for c in (r.get("by_counterparty") or [])
                     if c["overdue"] > 0][:3])
    if r["kind"] == "receivable":
        dso = f" DSO ~{f.n(r['dso_days'])} days." if r.get("dso_days") else ""
        return f.pick(
            f"Customers owe you {f.m(r['total_outstanding'])}; {f.m(r['overdue_total'])} is overdue across "
            f"{r['overdue_count']} invoice(s){': ' + who if who else ''}. Over 90 days: {f.m(r['buckets']['90+'])}.{dso}",
            f"ক্রেতাদের কাছে পাওনা {f.m(r['total_outstanding'])}; এর মধ্যে মেয়াদোত্তীর্ণ {f.m(r['overdue_total'])} "
            f"({f.n(r['overdue_count'])}টি ইনভয়েস){': ' + who if who else ''}। ৯০ দিনের বেশি: {f.m(r['buckets']['90+'])}।",
            f"Customer der kache pawna {f.m(r['total_outstanding'])}; overdue {f.m(r['overdue_total'])} "
            f"({r['overdue_count']} ta invoice){': ' + who if who else ''}. 90 diner beshi: {f.m(r['buckets']['90+'])}.")
    return f.pick(
        f"You owe suppliers {f.m(r['total_outstanding'])}; {f.m(r['overdue_total'])} is overdue"
        f"{': ' + who if who else ''}.",
        f"সরবরাহকারীদের দেনা {f.m(r['total_outstanding'])}; মেয়াদোত্তীর্ণ {f.m(r['overdue_total'])}{': ' + who if who else ''}।",
        f"Supplier der dena {f.m(r['total_outstanding'])}; overdue {f.m(r['overdue_total'])}{': ' + who if who else ''}.")


def c_costs(r, f: Fmt) -> str:
    items = []
    for d in (r.get("drivers") or [])[:4]:
        ch = f" ({'+' if d['change'] >= 0 else '-'}{f.m(abs(d['change']))})" if d["previous_amount"] else ""
        items.append(f"{f.cat(d['category'])} {f.m(d['amount'])} ({f.n(d['share_pct'])}%){ch}")
    return f.pick(f"Top costs for {r['period']} (total {f.m(r['total_expense'])}): " + "; ".join(items) + ".",
                  f"{r['period']} সময়ের প্রধান খরচ (মোট {f.m(r['total_expense'])}): " + "; ".join(items) + "।",
                  f"{r['period']} er boro khoroch (mot {f.m(r['total_expense'])}): " + "; ".join(items) + ".")


def c_change(r, f: Fmt) -> str:
    if f.lang == "en":
        return " ".join(r.get("explanation") or [])
    up = r["net_change"] >= 0
    drivers = "; ".join(f"{f.cat(d['category'])} {f.m(d['previous'])} → {f.m(d['current'])}"
                        for d in (r.get("drivers") or [])[:3])
    return f.pick("", f"নিট নগদ প্রবাহ {'বেড়েছে' if up else 'কমেছে'} {f.m(abs(r['net_change']))} "
                      f"({f.m(r['previous_net'])} থেকে {f.m(r['current_net'])})। প্রধান কারণ: {drivers}।",
                  f"Net cash flow {'bereche' if up else 'komeche'} {f.m(abs(r['net_change']))} "
                  f"({f.m(r['previous_net'])} theke {f.m(r['current_net'])}). Mul karon: {drivers}.")


def c_season(r, f: Fmt) -> str:
    ins = r.get("insights") or []
    if f.lang == "en":
        return " ".join(ins[:4]) or "No strong seasonal pattern yet."
    peaks = ", ".join(r.get("peaks") or []) or "-"
    up = "; ".join(f"{u['event']} ({f.n(u['days_away'])} " + f.pick("days", "দিন বাকি", "din baki") + ")"
                   for u in (r.get("upcoming_events") or [])[:2])
    return f.pick("", f"বিক্রির সর্বোচ্চ মাস: {peaks}। আসন্ন: {up or '-'}।",
                  f"Bikrir peak mash: {peaks}. Samne: {up or '-'}.")


def c_cash(r, f: Fmt) -> str:
    return f.pick(f"Your current balance is about {f.m(r['balance'])} (opening {f.m(r['opening_balance'])} + inflows "
                  f"{f.m(r['inflows_since_opening'])} - outflows {f.m(r['outflows_since_opening'])}).",
                  f"বর্তমান ব্যালেন্স প্রায় {f.m(r['balance'])} (শুরুর ব্যালেন্স {f.m(r['opening_balance'])} + আয় "
                  f"{f.m(r['inflows_since_opening'])} - খরচ {f.m(r['outflows_since_opening'])})।",
                  f"Ekhon balance prai {f.m(r['balance'])} (shuru {f.m(r['opening_balance'])} + ay "
                  f"{f.m(r['inflows_since_opening'])} - khoroch {f.m(r['outflows_since_opening'])}).")


def c_search(r, f: Fmt) -> str:
    rows = r.get("rows") or []
    lines = [f"- {x['date']}: {f.m(x['amount'])} {f.cat(x['category'])} {x['counterparty'] or x['description'][:40]} "
             f"[{', '.join(x['flags'])}]" for x in rows[:6]]
    head = f.pick(f"Found {r['count']} matching transaction(s), total {f.m(r['total_amount'])}:",
                  f"{f.n(r['count'])}টি লেনদেন পাওয়া গেছে, মোট {f.m(r['total_amount'])}:",
                  f"{r['count']} ta lenden paoa geche, mot {f.m(r['total_amount'])}:")
    return head + ("\n" + "\n".join(lines) if lines else "")


def c_loan(r, f: Fmt) -> str:
    return f.pick(
        f"EMI is {f.m(r['emi'])}/month. You'd repay {f.m(r['total_repayment'])} in total: interest "
        f"{f.m(r['total_interest'])} + fees {f.m(r['fees'])} = total cost of credit {f.m(r['total_cost_of_credit'])} "
        f"(effective APR {f.n(r['effective_apr_pct'])}%).",
        f"মাসিক কিস্তি {f.m(r['emi'])}। মোট পরিশোধ {f.m(r['total_repayment'])}: সুদ {f.m(r['total_interest'])} + ফি "
        f"{f.m(r['fees'])} = ঋণের মোট খরচ {f.m(r['total_cost_of_credit'])} (কার্যকর বার্ষিক হার {f.n(r['effective_apr_pct'])}%)।",
        f"Mashik kisti {f.m(r['emi'])}. Mot porishodh {f.m(r['total_repayment'])}: sud {f.m(r['total_interest'])} + fee "
        f"{f.m(r['fees'])} = loan er mot khoroch {f.m(r['total_cost_of_credit'])} (effective APR {f.n(r['effective_apr_pct'])}%).")


def c_add_txn(r, f: Fmt) -> str:
    e = r.get("entry") or {}
    if not r.get("recorded"):
        if r.get("missing"):
            miss = ", ".join(r["missing"])
            return f.pick(f"I couldn't record that yet - missing: {miss}. Please include the amount and whether "
                          f"money came in or went out.",
                          f"এখনো লেখা যায়নি - দরকার: {miss}। টাকার পরিমাণ এবং আয় না খরচ তা লিখুন।",
                          f"Ekhono lekha jayni - lagbe: {miss}. Taka koto ar ay na khoroch likhun.")
        return f.pick(f"Not recorded: it looks like a duplicate ({r.get('duplicate_warning')}).",
                      f"লেখা হয়নি: এটি আগের একটি লেনদেনের ডুপ্লিকেট মনে হচ্ছে।",
                      f"Lekha hoyni: eta duplicate mone hocche.")
    kind = f.pick("income" if e.get("direction") == "in" else "expense",
                  "আয়" if e.get("direction") == "in" else "খরচ", "ay" if e.get("direction") == "in" else "khoroch")
    warn = ""
    if r.get("anomaly_warning"):
        warn = f.pick(f" Note: this is unusual - {r['anomaly_warning']}.", " লক্ষ্য করুন: এটি অস্বাভাবিক বড়।",
                      " Kheyal korun: eta oshabhabik.")
    return f.pick(f"Recorded {kind}: {f.m(e.get('amount'))} as '{f.cat(e.get('category', ''))}' on {e.get('txn_date')} "
                  f"via {e.get('channel')}.{warn}",
                  f"লেখা হয়েছে ({kind}): {f.m(e.get('amount'))}, খাত '{f.cat(e.get('category', ''))}', তারিখ "
                  f"{f.n(e.get('txn_date'))}।{warn}",
                  f"Lekha holo ({kind}): {f.m(e.get('amount'))}, khat '{f.cat(e.get('category', ''))}', tarikh "
                  f"{e.get('txn_date')}.{warn}")


def c_forecast(r, f: Fmt) -> str:
    s = {x["days"]: x for x in r.get("summaries") or []}
    end = s.get(r["horizon_days"]) or list(s.values())[-1]
    s30 = s.get(30, end)
    neg = r.get("first_negative_date")
    low = r.get("first_below_threshold_date")
    thr = f.m(r["low_balance_threshold"])
    if neg:
        risk = f.pick(f" Warning: the balance may go below zero around {neg}.",
                      f" সতর্কতা: {f.n(neg)} নাগাদ ব্যালেন্স শূন্যের নিচে যেতে পারে।",
                      f" Sotorko: {neg} nagad balance shunner niche jete pare.")
    elif low:
        risk = f.pick(f" It dips below your safety level of {thr} around {low}.",
                      f" {f.n(low)} নাগাদ নিরাপত্তা সীমা {thr}-এর নিচে নামতে পারে।",
                      f" {low} nagad safety level {thr} er niche namte pare.")
    else:
        risk = f.pick(" No shortfall is expected.", " কোনো ঘাটতির আশঙ্কা নেই।", " Kono ghatti dekha jacche na.")
    runway = ""
    if r.get("runway_months") is not None:
        runway = f.pick(f" At the current burn, cash lasts about {f.n(r['runway_months'])} months.",
                        f" বর্তমান হারে নগদ প্রায় {f.n(r['runway_months'])} মাস চলবে।",
                        f" Ei hare cash prai {r['runway_months']} mash cholbe.")
    return f.pick(
        f"Cash now {f.m(r['start_balance'])}. Forecast: {f.m(s30['end_balance'])} in 30 days and "
        f"{f.m(end['end_balance'])} in {end['days']} days; lowest point {f.m(end['min_balance'])} on "
        f"{end['min_balance_date']}.{risk}{runway} (Estimate with an 80% range - see the chart.)",
        f"এখন নগদ {f.m(r['start_balance'])}। পূর্বাভাস: ৩০ দিনে {f.m(s30['end_balance'])}, {f.n(end['days'])} দিনে "
        f"{f.m(end['end_balance'])}; সর্বনিম্ন {f.m(end['min_balance'])} ({f.n(end['min_balance_date'])})।{risk}{runway}",
        f"Ekhon cash {f.m(r['start_balance'])}. Forecast: 30 dine {f.m(s30['end_balance'])}, {end['days']} dine "
        f"{f.m(end['end_balance'])}; sorbonimno {f.m(end['min_balance'])} ({end['min_balance_date']}).{risk}{runway}")


def c_whatif(r, f: Fmt) -> str:
    if f.lang == "en":
        return " ".join(r.get("explanation") or [])
    sc = "; ".join(x["description"] for x in r.get("scenarios") or [])
    ch = r["end_balance_change"]
    neg = r.get("scenario_first_negative_date")
    return f.pick(
        "",
        f"পরিস্থিতি: {sc}। {f.n(r['horizon_days'])} দিনে ব্যালেন্স হবে {f.m(r['scenario_end_balance'])} "
        f"(এখনকার পূর্বাভাস {f.m(r['baseline_end_balance'])}, পার্থক্য {f.m(ch)})। সর্বনিম্ন "
        f"{f.m(r['scenario_min_balance'])}।" + (f" সতর্কতা: {f.n(neg)} নাগাদ ঘাটতি।" if neg else ""),
        f"Scenario: {sc}. {r['horizon_days']} dine balance hobe {f.m(r['scenario_end_balance'])} "
        f"(ekhon er forecast {f.m(r['baseline_end_balance'])}, parthokko {f.m(ch)}). Sorbonimno "
        f"{f.m(r['scenario_min_balance'])}." + (f" Sotorko: {neg} nagad ghatti." if neg else ""))


def c_alerts(r, f: Fmt) -> str:
    items = r.get("alerts") or []
    if not items:
        return f.pick("No open alerts right now.", "এই মুহূর্তে কোনো সতর্কতা নেই।", "Ekhon kono alert nei.")
    lines = [f"- [{a['severity']}] {a['title']}" for a in items[:6]]
    head = f.pick(f"{r['count']} alert(s):", f"{f.n(r['count'])}টি সতর্কতা:", f"{r['count']} ta alert:")
    return head + "\n" + "\n".join(lines)


def c_digest(r, f: Fmt) -> str:
    k = r.get("kpis") or {}
    acts = "\n".join(f"- {a['title']}" for a in (r.get("actions") or [])[:4])
    alerts = "\n".join(f"- [{a['severity']}] {a['title']}" for a in (r.get("alerts") or [])[:5])
    out = f.pick(
        f"Cash now {f.m(k.get('cash_balance'))}; lowest in 30 days {f.m(k.get('forecast_min_30d'))}. This month: "
        f"income {f.m(k.get('income_this_month'))}, expenses {f.m(k.get('expense_this_month'))}. Overdue from "
        f"customers {f.m(k.get('receivables_overdue'))}.",
        f"এখন নগদ {f.m(k.get('cash_balance'))}; ৩০ দিনে সর্বনিম্ন {f.m(k.get('forecast_min_30d'))}। এই মাসে আয় "
        f"{f.m(k.get('income_this_month'))}, খরচ {f.m(k.get('expense_this_month'))}। ক্রেতাদের মেয়াদোত্তীর্ণ পাওনা "
        f"{f.m(k.get('receivables_overdue'))}।",
        f"Ekhon cash {f.m(k.get('cash_balance'))}; 30 dine sorbonimno {f.m(k.get('forecast_min_30d'))}. Ei mashe ay "
        f"{f.m(k.get('income_this_month'))}, khoroch {f.m(k.get('expense_this_month'))}. Customer der overdue pawna "
        f"{f.m(k.get('receivables_overdue'))}.")
    if alerts:
        out += "\n" + f.pick("Needs attention:", "মনোযোগ দরকার:", "Mone rakhun:") + "\n" + alerts
    if acts:
        out += "\n" + f.pick("Suggested next steps:", "পরামর্শ:", "Poramorsho:") + "\n" + acts
    return out


def c_ack(r, f: Fmt) -> str:
    return f.pick(f"Alert {r['alert_id']} marked {r['status']}.", f"সতর্কতা {f.n(r['alert_id'])} আপডেট হয়েছে।",
                  f"Alert {r['alert_id']} update hoyeche.")


def c_schedule(r, f: Fmt) -> str:
    return f.pick(f"Reminder scheduled for {r['due_date']}: \"{r['title']}\".",
                  f"{f.n(r['due_date'])} তারিখের জন্য রিমাইন্ডার সেট হয়েছে: \"{r['title']}\"।",
                  f"{r['due_date']} er jonno reminder set hoyeche: \"{r['title']}\".")


def c_match(r, f: Fmt) -> str:
    recs = r.get("recommendations") or []
    rej = r.get("rejected") or []
    head = f.pick(
        f"For {f.m(r['requested_amount'])} ({r['purpose'].replace('_', ' ')}): {len(recs)} option(s) fit, "
        f"{len(rej)} don't.",
        f"{f.m(r['requested_amount'])} ({r['purpose'].replace('_', ' ')}) এর জন্য: {f.n(len(recs))}টি বিকল্প মানানসই, "
        f"{f.n(len(rej))}টি নয়।",
        f"{f.m(r['requested_amount'])} ({r['purpose'].replace('_', ' ')}) er jonno: {len(recs)} ta option mile, "
        f"{len(rej)} ta mile na.")
    lines = []
    for i, m in enumerate(recs[:3], 1):
        cm = m.get("cost_mid") or {}
        lines.append(f.pick(
            f"{i}. {m['name']}: up to {f.m(m['offered_amount'])}, EMI ~{f.m(cm.get('emi'))} for {m['tenure_months']} "
            f"months (APR ~{f.n(cm.get('effective_apr_pct'))}%), total cost of credit ~"
            f"{f.m(cm.get('total_cost_of_credit'))}. Why: {'; '.join(m['reasons'][:2])}.",
            f"{f.n(i)}. {m['name']}: সর্বোচ্চ {f.m(m['offered_amount'])}, মাসিক কিস্তি ~{f.m(cm.get('emi'))} "
            f"({f.n(m['tenure_months'])} মাস), ঋণের মোট খরচ ~{f.m(cm.get('total_cost_of_credit'))}।",
            f"{i}. {m['name']}: shorbochho {f.m(m['offered_amount'])}, kisti ~{f.m(cm.get('emi'))} "
            f"({m['tenure_months']} mash), loan er mot khoroch ~{f.m(cm.get('total_cost_of_credit'))}."))
    if rej:
        r0 = rej[0]
        lines.append(f.pick(f"Not a fit, e.g. {r0['name']}: {r0['reasons'][0]}.",
                            f"মানানসই নয়, যেমন {r0['name']}: {r0['reasons'][0]}।",
                            f"Mile na, jemon {r0['name']}: {r0['reasons'][0]}."))
    lines.append(f.pick("All terms are illustrative - verify with the lender.",
                        "সব শর্ত উদাহরণমাত্র - ঋণদাতার কাছে যাচাই করুন।",
                        "Shob shorto udahoron matro - lender er kache jachai korun."))
    return head + "\n" + "\n".join(lines)


def c_readiness(r, f: Fmt) -> str:
    band = {"strong": ("strong", "শক্তিশালী", "strong"), "good": ("good", "ভালো", "bhalo"),
            "fair": ("fair", "মোটামুটি", "motamuti"), "needs_work": ("needs work", "উন্নতি দরকার", "unnoti dorkar")}
    b = band.get(r["band"], (r["band"],) * 3)
    weak = sorted(r.get("components") or [], key=lambda c: c["points"] - c["max_points"])[:2]
    weak_txt = ", ".join(f"{c['name']} {f.n(c['points'])}/{f.n(c['max_points'])}" for c in weak)
    tips = "\n".join(f"- {t}" for t in (r.get("top_tips") or [])[:3])
    return f.pick(f"Loan-readiness score: {r['score']:g}/100 ({b[0]}). Weakest areas: {weak_txt}.\nTop tips:\n{tips}",
                  f"ঋণ-প্রস্তুতি স্কোর: {f.n(r['score'])}/১০০ ({b[1]})। দুর্বল দিক: {weak_txt}।\n{tips}",
                  f"Loan-readiness score: {r['score']:g}/100 ({b[2]}). Durbol dik: {weak_txt}.\n{tips}")


def c_catalog(r, f: Fmt) -> str:
    lines = [f"- {p['name']} ({p['lender_type']}): {f.m(p['amount_range'][0])}-{f.m(p['amount_range'][1])}, "
             f"{f.n(p['rate_range_pct'][0])}-{f.n(p['rate_range_pct'][1])}% [{p['verify_label']}]"
             for p in (r.get("products") or [])[:8]]
    return f.pick(f"{r['count']} financing types in the catalog:", f"{f.n(r['count'])} ধরনের অর্থায়ন:",
                  f"{r['count']} dhoroner financing:") + "\n" + "\n".join(lines)


COMPOSERS: dict[str, Callable[[dict[str, Any], Fmt], str]] = {
    "match_financing": c_match, "loan_readiness_score": c_readiness, "get_financing_catalog": c_catalog,
    "forecast_cash_flow": c_forecast, "run_what_if": c_whatif, "list_alerts": c_alerts, "get_digest": c_digest,
    "acknowledge_alert": c_ack, "schedule_alert": c_schedule,
    "get_financial_summary": c_summary, "get_profitability": c_profit, "get_break_even": c_break_even,
    "get_aging": c_aging, "get_cost_drivers": c_costs, "explain_change": c_change, "get_seasonality": c_season,
    "get_cash_position": c_cash, "search_transactions": c_search, "calculate_loan": c_loan,
    "add_transaction": c_add_txn,
}
