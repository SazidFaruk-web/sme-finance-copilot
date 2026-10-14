"""Responsible-AI guardrails: refuse fraud, tax evasion, fake documents, laundering.

A deterministic pre-check runs before any model call, so refusal does not depend on the
model's alignment. The system prompt repeats the same policy for defence in depth.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_RULES: list[tuple[str, str]] = [
    ("fake_documents", r"\b(fake|forged?|forging|fabricat\w*|counterfeit|doctor(ed)?|bogus)\b.{0,40}\b(invoice|invoices|bank statement|statement|receipt|document|documents|trade licen[cs]e|tin|certificate|salary slip|papers?)\b"),
    ("fake_documents", r"\b(make|create|generate|edit|change)\b.{0,30}\b(bank statement|trade licen[cs]e|tin certificate)\b.{0,40}\b(look|show|appear|higher|bigger|more)\b"),
    ("inflate_for_loan", r"\b(inflate|exaggerate|pump up|fake|boost)\b.{0,30}\b(revenue|sales|income|turnover|profit|numbers)\b.{0,40}\b(loan|bank|lender|approval)\b"),
    ("tax_evasion", r"\b(evade|evasion|dodge|avoid paying|hide|conceal|under-?report|skip)\b.{0,30}\b(tax|taxes|vat|income tax|nbr)\b"),
    ("tax_evasion", r"\b(hide|conceal|under-?report)\b.{0,30}\b(income|sales|revenue)\b.{0,30}\b(from|to)\b.{0,10}\b(tax|vat|nbr|government)\b"),
    ("two_books", r"\b(two|2|double|separate)\s+(sets? of )?(books|accounts|ledgers)\b"),
    ("laundering", r"\b(launder\w*|money laundering|clean (the )?black money|structure (the )?deposits|smurf\w*)\b"),
    ("bribery", r"\b(bribe|bribing|speed money|ghush)\b"),
    ("bn_fake", r"(জাল|নকল|ভুয়া).{0,20}(কাগজ|ডকুমেন্ট|ইনভয়েস|স্টেটমেন্ট|লাইসেন্স|রশিদ)"),
    ("bn_tax", r"(ট্যাক্স|কর|ভ্যাট).{0,20}(ফাঁকি|লুকা|এড়া)"),
    ("bn_black_money", r"কালো টাকা.{0,15}(সাদা|বৈধ)"),
    ("banglish_fake", r"\b(jal|nokol|bhuya|vuya)\b.{0,20}\b(kagoj|document|invoice|statement|license|roshid)\b"),
    ("banglish_tax", r"\b(tax|vat|kor)\b.{0,15}\b(fanki|lukabo|lukano|na dite)\b"),
    ("banglish_black_money", r"\bkalo taka\b.{0,15}\b(sada|white)\b"),
]
_COMPILED = [(n, re.compile(rx, re.I | re.S)) for n, rx in _RULES]

REFUSALS = {
    "en": ("I can't help with that: it would involve {what}, which is illegal and could seriously harm you "
           "and your business. I can help you legitimately instead: organise your real records, reduce tax "
           "through allowed deductions with a licensed tax adviser, or improve your genuine loan-readiness score."),
    "bn": ("দুঃখিত, এতে সাহায্য করতে পারছি না: এটি {what}, যা বেআইনি এবং আপনার ব্যবসার বড় ক্ষতি করতে পারে। "
           "বরং আমি বৈধভাবে সাহায্য করতে পারি: আসল হিসাব গুছানো, লাইসেন্সপ্রাপ্ত কর পরামর্শকের সাথে বৈধ ছাড় নেওয়া, "
           "অথবা আপনার ঋণ-প্রস্তুতি স্কোর সত্যিকারভাবে বাড়ানো।"),
    "banglish": ("Dukkhito, eta te help korte parbo na: eta {what}, ja beaini ebong apnar byabshar khoti korte pare. "
                 "Borong ami boidho vabe help korte pari: ashol hisab gochano, licensed tax adviser er sathe boidho "
                 "chhar neya, ba apnar loan-readiness score ashole barano."),
}
WHAT = {
    "fake_documents": {"en": "creating or altering documents", "bn": "জাল কাগজপত্র তৈরি বা পরিবর্তন",
                       "banglish": "jal kagojpotro toiri ba bodlano"},
    "inflate_for_loan": {"en": "misrepresenting your numbers to a lender", "bn": "ঋণদাতার কাছে ভুল তথ্য দেওয়া",
                         "banglish": "lender ke vul tottho deya"},
    "tax_evasion": {"en": "tax evasion", "bn": "কর ফাঁকি", "banglish": "tax fanki"},
    "two_books": {"en": "keeping a second set of books to mislead authorities", "bn": "দুই সেট হিসাব রাখা",
                  "banglish": "dui set hisab rakha"},
    "laundering": {"en": "money laundering", "bn": "অর্থ পাচার / মানি লন্ডারিং", "banglish": "money laundering"},
    "bribery": {"en": "bribery", "bn": "ঘুষ", "banglish": "ghush"},
}


@dataclass
class GuardResult:
    refused: bool
    category: str = ""
    message: str = ""


def _family(name: str) -> str:
    if name.endswith("fake"):
        return "fake_documents"
    if name.endswith("tax"):
        return "tax_evasion"
    if name.endswith("black_money"):
        return "laundering"
    return name


def check_request(text: str, language: str = "en") -> GuardResult:
    for name, rx in _COMPILED:
        if rx.search(text or ""):
            fam = _family(name)
            lang = language if language in REFUSALS else "en"
            what = WHAT.get(fam, WHAT["fake_documents"])[lang]
            return GuardResult(True, fam, REFUSALS[lang].format(what=what))
    return GuardResult(False)


DISCLAIMER = {
    "en": "Decision support only, not licensed financial advice. Financing terms shown are illustrative; "
          "verify with the lender. Approval is never guaranteed.",
    "bn": "এটি শুধু সিদ্ধান্ত নিতে সহায়তা, লাইসেন্সপ্রাপ্ত আর্থিক পরামর্শ নয়। ঋণের শর্তগুলো উদাহরণমাত্র; "
          "ঋণদাতার কাছে যাচাই করুন। অনুমোদনের কোনো নিশ্চয়তা নেই।",
    "banglish": "Eta shudhu decision support, licensed financial advice na. Loan er shorto gulo udahoron matro; "
                "lender er kache jachai korun. Approval er kono guarantee nei.",
}
