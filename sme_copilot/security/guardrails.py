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
    # Chinese (the interface language since 2026-10): same families, written to leave legal questions alone
    # ("如何合法减少税费", "怎么开发票").
    ("zh_fake", r"(假的?|伪造|造假|虚假|仿造|做假|编造).{0,20}(发票|银行流水|流水|对账单|收据|单据|文件|证明|营业执照|执照|合同|工资单|报表)"),
    ("inflate_for_loan", r"(虚报|夸大|多报|虚增|做高|美化|编造).{0,15}(收入|销售额?|营业额|利润|流水).{0,30}(贷款|银行|放款|审批)"),
    ("zh_tax", r"逃税|偷税|漏税|(隐瞒|瞒报|少报|不报).{0,15}(收入|销售额?|营业额|增值税|税)"),
    ("two_books", r"两套账|两本账|做假账|内外账|阴阳账"),
    ("zh_black_money", r"洗钱|黑钱|洗白.{0,6}(钱|资金|收入)"),
    ("bribery", r"行贿|贿赂"),
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
    "zh": ("我无法帮助您做这件事：这涉及{what}，属于违法行为，可能会严重损害您和您的生意。我可以用合法的方式帮助您："
           "整理真实的记录、在持牌税务顾问的指导下利用允许的扣除项减少税款，或切实提高您的贷款准备度评分。"),
}
WHAT = {
    "fake_documents": {"en": "creating or altering documents", "bn": "জাল কাগজপত্র তৈরি বা পরিবর্তন",
                       "banglish": "jal kagojpotro toiri ba bodlano", "zh": "制作或篡改文件"},
    "inflate_for_loan": {"en": "misrepresenting your numbers to a lender", "bn": "ঋণদাতার কাছে ভুল তথ্য দেওয়া",
                         "banglish": "lender ke vul tottho deya", "zh": "向贷款机构虚报数据"},
    "tax_evasion": {"en": "tax evasion", "bn": "কর ফাঁকি", "banglish": "tax fanki", "zh": "逃税"},
    "two_books": {"en": "keeping a second set of books to mislead authorities", "bn": "দুই সেট হিসাব রাখা",
                  "banglish": "dui set hisab rakha", "zh": "做两套账来误导有关部门"},
    "laundering": {"en": "money laundering", "bn": "অর্থ পাচার / মানি লন্ডারিং", "banglish": "money laundering", "zh": "洗钱"},
    "bribery": {"en": "bribery", "bn": "ঘুষ", "banglish": "ghush", "zh": "行贿"},
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
