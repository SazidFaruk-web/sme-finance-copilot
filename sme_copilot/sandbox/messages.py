"""Deterministic message templates for reminders and invoice follow-ups (English and Bangla).

Templates (not free LLM text) are used for anything sent to a customer, so tone and facts are
controlled; an LLM may suggest edits but the owner approves the final draft.
"""
from __future__ import annotations

from datetime import date

from sme_copilot.tools.money import format_bdt
from sme_copilot.tools.textnorm import ascii_to_bn_digits

FOLLOWUP = {
    ("en", "polite"): (
        "Payment reminder: invoice {inv}",
        "Dear {party},\n\nI hope you are well. This is a friendly reminder that invoice {inv} for {amount} was due on "
        "{due}{late}. We would be grateful if you could arrange payment at your earliest convenience.\n\n"
        "You can pay by bank transfer or bKash to our usual account. If you have already paid, please ignore this "
        "message and accept our thanks.\n\nThank you for your continued business.\n{biz}"),
    ("en", "firm"): (
        "Overdue invoice {inv} - please pay by {by}",
        "Dear {party},\n\nOur records show invoice {inv} for {amount}, due on {due}, is still unpaid{late}. Please "
        "settle it by {by}. If there is a problem with the invoice, let us know so we can resolve it quickly.\n\n"
        "Regards,\n{biz}"),
    ("en", "final"): (
        "Final reminder: invoice {inv}",
        "Dear {party},\n\nDespite earlier reminders, invoice {inv} for {amount} (due {due}{late}) remains unpaid. "
        "Please pay by {by}. If we do not hear from you, we may have to pause further deliveries on credit.\n\n"
        "Regards,\n{biz}"),
    ("bn", "polite"): (
        "পেমেন্টের অনুরোধ: ইনভয়েস {inv}",
        "প্রিয় {party},\n\nআশা করি ভালো আছেন। বিনীতভাবে মনে করিয়ে দিচ্ছি যে ইনভয়েস {inv}-এর {amount} পরিশোধের তারিখ ছিল "
        "{due}{late}। সুবিধামতো দ্রুত পরিশোধ করলে কৃতজ্ঞ থাকব।\n\nব্যাংক ট্রান্সফার বা বিকাশে আমাদের পরিচিত অ্যাকাউন্টে "
        "পাঠাতে পারেন। ইতিমধ্যে পরিশোধ করে থাকলে এই বার্তাটি উপেক্ষা করুন, ধন্যবাদ।\n\n{biz}"),
    ("bn", "firm"): (
        "মেয়াদোত্তীর্ণ ইনভয়েস {inv} - {by} এর মধ্যে পরিশোধ করুন",
        "প্রিয় {party},\n\nআমাদের হিসাবে ইনভয়েস {inv}-এর {amount} (পরিশোধের তারিখ {due}) এখনো বাকি{late}। অনুগ্রহ করে "
        "{by} এর মধ্যে পরিশোধ করুন। ইনভয়েসে কোনো সমস্যা থাকলে জানাবেন।\n\n{biz}"),
    ("bn", "final"): (
        "শেষ অনুরোধ: ইনভয়েস {inv}",
        "প্রিয় {party},\n\nআগের অনুরোধের পরও ইনভয়েস {inv}-এর {amount} (তারিখ {due}{late}) পরিশোধ হয়নি। অনুগ্রহ করে {by} "
        "এর মধ্যে পরিশোধ করুন, নইলে বাকিতে নতুন মাল সরবরাহ সাময়িকভাবে বন্ধ রাখতে হতে পারে।\n\n{biz}"),
}

SMS = {
    "en": "Reminder from {biz}: invoice {inv} for {amount} was due {due}. Please pay at your earliest convenience. "
          "Thank you.",
    "bn": "{biz}: ইনভয়েস {inv}-এর {amount} পরিশোধের তারিখ ছিল {due}। অনুগ্রহ করে দ্রুত পরিশোধ করুন। ধন্যবাদ।",
}


def _fmt(lang: str, amount: float, due: date, days_late: int, style: str) -> tuple[str, str, str]:
    bn = lang == "bn"
    amt = format_bdt(amount, style=style, bangla_digits=bn)
    due_s = due.strftime("%d %b %Y")
    late = ""
    if days_late > 0:
        late = f" ({days_late} দিন আগে)" if bn else f" ({days_late} days ago)"
    if bn:
        due_s = ascii_to_bn_digits(due.strftime("%d/%m/%Y"))
        late = ascii_to_bn_digits(late)
    return amt, due_s, late


def followup(lang: str, tone: str, *, party: str, inv: str, amount: float, due: date, as_of: date, biz: str,
             pay_by: date, style: str = "lakh") -> tuple[str, str]:
    lang = "bn" if lang == "bn" else "en"
    subj_t, body_t = FOLLOWUP[(lang, tone if tone in ("polite", "firm", "final") else "polite")]
    amt, due_s, late = _fmt(lang, amount, due, (as_of - due).days, style)
    by = ascii_to_bn_digits(pay_by.strftime("%d/%m/%Y")) if lang == "bn" else pay_by.strftime("%d %b %Y")
    vals = dict(party=party, inv=inv, amount=amt, due=due_s, late=late, biz=biz, by=by)
    return subj_t.format(**vals), body_t.format(**vals)


def sms(lang: str, *, biz: str, inv: str, amount: float, due: date, style: str = "lakh") -> str:
    lang = "bn" if lang == "bn" else "en"
    amt, due_s, _ = _fmt(lang, amount, due, 0, style)
    return SMS[lang].format(biz=biz, inv=inv, amount=amt, due=due_s)
