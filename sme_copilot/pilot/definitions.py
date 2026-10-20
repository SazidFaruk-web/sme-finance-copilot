"""Reviewed UI vocabulary; a model can select IDs, never executable markup."""
from __future__ import annotations

def tr(en, bn):
    return {"en": en, "bn": bn}


KINDS = {
    "strategy": tr("Plan for the future", "ভবিষ্যতের পরিকল্পনা"),
    "record": tr("Record or check money", "হিসাব লিখুন বা টাকা মেলান"),
    "collect": tr("Collect a customer payment", "ক্রেতার বাকি আদায় করুন"),
    "shortfall": tr("Plan an upcoming payment", "সামনের পেমেন্টের পরিকল্পনা"),
    "loan": tr("Check a loan quote", "ঋণের প্রস্তাব যাচাই"),
    "stock": tr("Try a new product", "নতুন পণ্য পরীক্ষার পরিকল্পনা"),
    "paperwork": tr("Prepare business paperwork", "ব্যবসার কাগজপত্র প্রস্তুত করুন"),
}


def q(key, en, bn, type="money", options=None, **kw):
    return {"id": key, "label": tr(en, bn), "type": type, "options": options or [], **kw}


def opts(*rows):
    return [{"value": k, "label": tr(en, bn)} for k, en, bn in rows]


YES = opts(("yes", "Yes", "হ্যাঁ"), ("no", "No", "না"))
CHANNELS = opts(("cash", "Cash", "নগদ"), ("bank", "Bank", "ব্যাংক"), ("bkash", "bKash", "বিকাশ"),
                ("nagad", "Nagad", "নগদ ওয়ালেট"), ("rocket", "Rocket", "রকেট"))
RECORD_TYPES = opts(("sale", "Sale / daily sales", "বিক্রি / দিনের মোট বিক্রি"),
    ("expense", "Business expense", "ব্যবসার খরচ"), ("purchase", "Bought stock", "পণ্য কেনা"),
    ("borrow", "Received a loan", "ঋণের টাকা পেয়েছি"), ("repay", "Repaid a loan", "ঋণ পরিশোধ করেছি"),
    ("withdraw", "Took money home", "সংসারের জন্য নিয়েছি"), ("transfer", "Moved my own money", "নিজের টাকা স্থানান্তর"),
    ("advance", "Customer advance", "ক্রেতার অগ্রিম"), ("refund", "Refund to a customer", "ক্রেতাকে টাকা ফেরত"),
    ("check", "Count and check money", "টাকা গুনে হিসাব মেলান"))


def questions(kind, a, snapshot):
    """Conditional sequence: changing an early answer removes irrelevant downstream steps."""
    if kind == "strategy":
        from .strategy import strategy_questions
        return strategy_questions(a, snapshot)
    dateq = q("date", "When did this happen?", "কবে হয়েছে?", "date")
    due = q("due_date", "When is it due?", "কবে দিতে হবে?", "date")
    follow = q("review_date", "When should we remind you?", "কবে মনে করিয়ে দেব?", "date")
    current = q("cash", "How much business money do you have now?", "এখন ব্যবসার জন্য কত টাকা আছে?",
                suggestion=snapshot["cash"])
    reserve = q("reserve", "How much money must remain untouched?", "কত টাকা হাতে রাখতেই হবে?")
    if kind == "record":
        qs = [q("record_type", "What happened?", "কী হয়েছে?", "choice", RECORD_TYPES), dateq]
        t = a.get("record_type")
        if t == "check":
            return qs + [current, q("note", "Anything missing from your records?", "কোনো হিসাব বাদ পড়েছে?", "text")]
        qs += [q("amount", "How much in total?", "মোট কত টাকা?", min=0.01),
               q("description", "What was it for?", "কী জন্য?", "text")]
        if t in ("sale", "purchase"):
            qs += [q("settled", "Was money paid now?", "এখনই টাকা দেওয়া হয়েছে?", "choice",
                     opts(("yes", "Yes", "হ্যাঁ"), ("partial", "Part of it", "কিছুটা"), ("no", "No", "না")))]
        if a.get("settled") == "partial":
            qs += [q("paid_now", "How much was paid now?", "এখন কত টাকা দেওয়া হয়েছে?", min=0.01)]
        if a.get("settled") in ("no", "partial") or t == "advance":
            qs += [q("party", "Customer or supplier name?", "ক্রেতা বা সরবরাহকারীর নাম?", "text"), due]
        if t == "repay":
            qs += [q("interest", "How much of this is interest or fees?", "এর মধ্যে সুদ বা চার্জ কত টাকা?")]
        if a.get("settled") != "no":
            qs += [q("channel", "Which account?", "কোন হিসাবে?", "choice", CHANNELS)]
        if t == "transfer":
            qs += [q("to_channel", "Which account received it?", "কোন হিসাবে জমা হয়েছে?", "choice", CHANNELS)]
        return qs
    if kind == "collect":
        return [q("invoice_id", "Which customer payment?", "কোন ক্রেতার বাকি?", "choice",
                  [{"value": str(i["id"]), "label": tr(f'{i["name"]} · ৳{i["outstanding"]:,.0f}',
                      f'{i["name"]} · ৳{i["outstanding"]:,.0f}')} for i in snapshot["receivables"]]),
                q("disputed", "Has the customer disputed the bill?", "ক্রেতা কি বিল নিয়ে আপত্তি করেছেন?", "choice", YES),
                q("promised_date", "When did they promise to pay?", "কবে দেওয়ার কথা বলেছেন?", "date"), follow]
    if kind == "shortfall":
        return [q("purpose", "What needs to be paid?", "কী জন্য টাকা দিতে হবে?", "text"),
                q("amount", "How much is needed?", "কত টাকা দরকার?", min=0.01), due, current,
                q("essentials", "Other essential payments before then?", "এর আগে অন্য জরুরি পেমেন্ট কত?"),
                q("collections", "Customer payments you expect before then?", "এর আগে ক্রেতার কাছ থেকে কত পাওয়ার আশা করছেন?"),
                q("existing_debt", "Debt payments before then?", "এর আগে ঋণের কিস্তি কত?"), reserve, follow]
    if kind == "loan":
        return [q("lender", "Who gave you this quote?", "কে ঋণের প্রস্তাব দিয়েছেন?", "text"),
                q("quote_source", "Where and when did you receive this offer?", "কোথায় ও কবে এই প্রস্তাব পেয়েছেন?", "text"),
                q("principal", "Loan amount before fees?", "চার্জ কাটার আগে ঋণের পরিমাণ?", min=0.01),
                q("fees", "Fees deducted or paid upfront?", "শুরুতেই কাটা বা দেওয়া চার্জ কত?"),
                q("schedule", "Add every repayment from the quote", "প্রস্তাব অনুযায়ী সব কিস্তি যোগ করুন", "schedule"),
                q("quote_complete", "Are all charges and repayments included?", "সব চার্জ ও কিস্তি কি লেখা হয়েছে?", "choice", YES),
                current, q("purchase", "How much will you spend when the loan arrives?", "ঋণ পেলে শুরুতেই কত খরচ করবেন?"),
                q("income", "Cash received in a usual month?", "স্বাভাবিক মাসে হাতে কত টাকা আসে?"),
                q("slow_income", "Cash received in a slow month?", "বিক্রি কম হলে মাসে কত টাকা আসে?"),
                q("cash_timing", "When does money usually arrive?", "সাধারণত কখন টাকা আসে?", "choice",
                  opts(("daily", "Most days, fairly steadily", "প্রায় প্রতিদিন, মোটামুটি নিয়মিত"),
                       ("uneven", "Seasonal or on a few dates", "মৌসুমে বা কিছু নির্দিষ্ট দিনে"))),
                *([q("income_schedule", "Expected receipts across the whole loan term", "পুরো ঋণের মেয়াদে টাকা পাওয়ার তারিখ", "schedule")] if a.get("cash_timing") == "uneven" else []),
                q("expenses", "Essential business spending each month?", "মাসে জরুরি ব্যবসার খরচ কত?"),
                q("household", "Necessary money taken home each month?", "সংসারের জন্য মাসে কত নিতেই হবে?"),
                q("existing_debt", "Existing loan payments each month?", "চলমান ঋণের মাসিক কিস্তি কত?"),
                q("other_schedule", "Extra dated payments, not included in monthly costs?", "মাসিক খরচে ধরা হয়নি এমন বাড়তি পেমেন্ট?", "schedule"),
                reserve, q("facts_complete", "Have you included all debts and essential costs?", "সব ঋণ ও জরুরি খরচ কি অন্তর্ভুক্ত করেছেন?", "choice", YES),
                q("security", "What is pledged or guaranteed?", "জামানত বা গ্যারান্টি কী দিতে হবে?", "text"), follow]
    if kind == "stock":
        return [q("product", "Which product would you like to try?", "কোন পণ্য পরীক্ষা করতে চান?", "text"),
                q("quantity", "How many items in this batch?", "এই চালানে কতটি পণ্য?", "number", min=1, max=100000),
                q("unit_cost", "Purchase cost per item?", "প্রতিটি পণ্যের কেনার দাম?", min=0.01),
                q("delivery", "Total delivery and setup cost?", "মোট পরিবহন ও প্রস্তুতির খরচ?"),
                q("price", "Selling price per item?", "প্রতিটি পণ্যের বিক্রির দাম?", min=0.01),
                q("selling_cost", "Packaging and other selling cost per item?", "প্রতি পণ্যের প্যাকেট ও বিক্রির অন্য খরচ?"),
                q("expected", "How many could sell before your review date?", "পর্যালোচনার তারিখের আগে কতটি বিক্রি হতে পারে?", "number"),
                q("evidence", "What makes you expect these sales?", "এই বিক্রির আশা করার কারণ কী?", "text"),
                q("risk", "Could items expire, be returned, or remain unsold?", "মেয়াদ শেষ, ফেরত বা অবিক্রীত থাকার ঝুঁকি কী?", "text"),
                q("collection_days", "Days from a sale until you get paid?", "বিক্রির কত দিন পর টাকা পাবেন?", "number", max=365),
                current, reserve, follow]
    if kind == "paperwork":
        return [q("topic", "What paperwork do you need help with?", "কোন কাগজপত্রে সাহায্য দরকার?", "choice",
                  opts(("trade", "Trade licence", "ট্রেড লাইসেন্স"), ("income_tax", "Income tax", "আয়কর"), ("vat", "VAT", "ভ্যাট"))),
                q("authority", "Which local authority covers your shop?", "দোকানটি কোন স্থানীয় কর্তৃপক্ষের অধীনে?", "choice",
                  opts(("dscc", "Dhaka South", "ঢাকা দক্ষিণ"), ("other", "Another authority", "অন্য কর্তৃপক্ষ"))),
                q("activity", "What does the shop sell or do?", "দোকানে কী বিক্রি বা কাজ হয়?", "text"),
                q("registered", "Do you already have this registration?", "এই নিবন্ধন কি আগে থেকেই আছে?", "choice", YES),
                q("period", "Which licence or tax period?", "লাইসেন্স বা করের কোন সময়কাল?", "text"),
                q("documents", "Which documents do you already have?", "কোন কাগজপত্র ইতিমধ্যে আছে?", "text"),
                q("deadline", "Deadline shown on your document or notice?", "কাগজ বা নোটিশে শেষ তারিখ কত?", "date"),
                q("deadline_source", "Where is that deadline recorded?", "শেষ তারিখ কোথায় লেখা আছে?", "text"),
                q("request", "What would you like the office to help with?", "কোন বিষয়ে দপ্তরের সাহায্য চান?", "text")]
    raise ValueError("unknown workflow")
