from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select

from sme_copilot.models import Alert, Business, Invoice, InvoicePayment, Obligation, Transaction
from .calculations import loan, money, stock
from .definitions import KINDS, questions, tr
from .knowledge import sources
from .models import CaseDocument, ReminderJob
from .question_model import next_question


def fail(code, status=422):
    raise HTTPException(status, {"code": code})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def snapshot(db, bid, today):
    b = db.get(Business, bid)
    tx = list(db.scalars(select(Transaction).where(Transaction.business_id == bid,
                    Transaction.txn_date <= today, Transaction.is_duplicate.is_(False)).order_by(Transaction.id)))
    invoices = list(db.scalars(select(Invoice).where(Invoice.business_id == bid).order_by(Invoice.id)))
    obligations = list(db.scalars(select(Obligation).where(Obligation.business_id == bid, Obligation.active.is_(True))))
    cash = float(b.opening_cash_balance) + sum(float(t.amount) * (1 if t.direction == "in" else -1)
           for t in tx if b.opening_balance_date is None or t.txn_date > b.opening_balance_date)
    def inv(i):
        return {"id": i.id, "name": i.counterparty, "outstanding": money(max(0, i.amount - i.amount_paid)),
                "due_date": i.due_date.isoformat(), "status": i.status, "kind": i.kind}
    data = {"business": b.name, "today": today.isoformat(), "cash": money(cash), "record_count": len(tx),
            "opening_confirmed": b.opening_balance_date is not None,
            "receivables": [inv(i) for i in invoices if i.kind == "receivable" and i.status not in ("draft", "paid", "written_off") and i.amount > i.amount_paid],
            "payables": [inv(i) for i in invoices if i.kind == "payable" and i.status not in ("draft", "paid", "written_off") and i.amount > i.amount_paid],
            "obligations": [{"id": o.id, "name": o.name, "amount": o.amount, "date": o.next_due.isoformat()} for o in obligations]}
    data["fingerprint"] = digest([data, [(t.id, t.txn_date, t.amount, t.direction, t.category) for t in tx],
                                 sources(db, today), b.sector, b.district, (b.prefs or {}).get("about")])
    return data


def validate(question, value, today):
    if value is None:  # explicit "I don't know" is preserved, never silently converted to zero
        return None
    kind = question["type"]
    if kind in ("money", "number", "decimal"):
        try:
            if isinstance(value, bool):
                raise ValueError()
            n = Decimal(str(value).translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")).replace(",", ""))
            if not n.is_finite() or not Decimal(str(question.get("min", 0))) <= n <= Decimal(str(question.get("max", 1e8))):
                raise ValueError()
            if kind == "number" and n != n.to_integral_value():
                raise ValueError()
            return int(n) if kind == "number" else money(n)
        except (ValueError, InvalidOperation):
            fail("invalid_number")
    if kind == "choice":
        if str(value) not in [o["value"] for o in question["options"]]:
            fail("invalid_choice")
        return str(value)
    if kind == "date":
        try:
            d = date.fromisoformat(value)
            if not date(2000, 1, 1) <= d <= today + timedelta(days=3660):
                raise ValueError()
            if question["id"] == "date" and d > today:
                raise ValueError()
            if question["id"] == "review_date" and d < today:
                raise ValueError()
            return d.isoformat()
        except (ValueError, TypeError):
            fail("invalid_date")
    if kind == "schedule":
        if not isinstance(value, list) or len(value) > 600:
            fail("invalid_schedule")
        cleaned = []
        for p in value:
            if not isinstance(p, dict) or set(p) != {"date", "amount"}:
                fail("invalid_schedule")
            d = validate({"type": "date", "id": "payment"}, p["date"], today)
            amount = validate({"type": "money", "min": .01}, p["amount"], today)
            if d is None or amount is None or d < today.isoformat():
                fail("invalid_schedule")
            cleaned.append({"date": d, "amount": amount})
        return sorted(cleaned, key=lambda p: p["date"])
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2000:
        fail("invalid_text")
    return value.strip()


def calculate(case, snap):
    a, kind = case.answers, case.kind
    if kind == "strategy":
        from .strategy import assess
        return assess(a, date.fromisoformat(snap["today"]))
    if kind == "loan":
        result = loan(a, date.fromisoformat(snap["today"]))
        return {**result, "review_required": True}
    if kind == "stock":
        return stock(a)
    if kind == "shortfall":
        keys = ("amount", "cash", "essentials", "collections", "existing_debt", "reserve")
        if any(a.get(k) is None for k in keys):
            return {"status": "need_information", "metrics": {}}
        available = a["cash"] - a["essentials"] - a["existing_debt"] - a["reserve"]
        return {"status": "shortfall" if available < a["amount"] else "covered",
            "metrics": {"available_after_commitments": money(available), "needed": a["amount"],
                        "gap_now": money(max(0, a["amount"] - available)),
                        "gap_if_collected": money(max(0, a["amount"] - available - a["collections"]))}}
    if kind == "record" and a.get("record_type") == "check":
        difference = money(a["cash"] - snap["cash"]) if a.get("cash") is not None else None
        return {"status": "check_records" if difference else "recorded", "metrics": {"recorded_cash": snap["cash"], "counted_cash": a.get("cash"), "difference": difference}}
    if kind == "collect":
        selected = next((i for i in snap["receivables"] if str(i["id"]) == a.get("invoice_id")), None)
        return {"status": "resolve_dispute" if a.get("disputed") == "yes" else "prepare_message",
                "metrics": {"outstanding": selected["outstanding"] if selected else None}, "invoice": selected}
    if kind == "paperwork":
        return {"status": "verify_requirements", "metrics": {}, "review_required": True,
            "checklist": [
                {"label": tr("Registration", "নিবন্ধন"), "detail": tr("Owner reports an existing registration" if a.get("registered") == "yes" else "Check whether registration applies", "মালিক বলেছেন নিবন্ধন আছে" if a.get("registered") == "yes" else "নিবন্ধন প্রযোজ্য কি না দেখুন")},
                {"label": tr("Filing requirements and prescribed form", "দাখিলের শর্ত ও নির্ধারিত ফরম"), "detail": tr("Confirm with the authority or pilot reviewer", "কর্তৃপক্ষ বা পাইলট পর্যালোচককে দিয়ে যাচাই করুন")},
                {"label": tr("Tax or fee payment", "কর বা ফি দেওয়া"), "detail": tr("Check separately; registration does not establish the amount due", "আলাদাভাবে যাচাই করুন; নিবন্ধন থাকলেই করের পরিমাণ ঠিক হয় না")},
                {"label": tr("Documents you have", "আপনার কাছে থাকা কাগজ"), "detail": tr(a.get("documents") or "Not yet listed", a.get("documents") or "এখনও লেখা হয়নি")},
                {"label": tr("Deadline evidence", "শেষ তারিখের প্রমাণ"), "detail": tr((a.get("deadline") + " · " + a.get("deadline_source")) if a.get("deadline") and a.get("deadline_source") else "No verified deadline yet", (a.get("deadline") + " · " + a.get("deadline_source")) if a.get("deadline") and a.get("deadline_source") else "এখনও যাচাই করা শেষ তারিখ নেই")},
                {"label": tr("After submitting", "দাখিলের পরে"), "detail": tr("Keep the acknowledgement, follow up, then record acceptance", "প্রাপ্তিস্বীকার রাখুন, খোঁজ নিন, তারপর গৃহীত হলে লিখুন")}
            ]}
    return {"status": "review_record", "metrics": {"amount": a.get("amount")}}


def options(case, result):
    if case.status == "completed":
        return []
    if case.kind == "strategy":
        return [{"id": "save", "label": tr("Save plan for review", "পর্যালোচনার জন্য পরিকল্পনা রাখুন")},
                {"id": "supplier", "label": tr("Prepare a supplier enquiry", "সরবরাহকারীর জন্য প্রশ্ন তৈরি")},
                {"id": "wait", "label": tr("Wait and review later", "অপেক্ষা করে আবার দেখুন")}]
    if case.kind == "record":
        return [{"id": "save", "label": tr("Review and save", "দেখে সংরক্ষণ করুন")}]
    if case.kind == "collect":
        return [{"id": "draft", "label": tr("Prepare a message", "বার্তা প্রস্তুত করুন")}]
    if case.kind == "paperwork":
        return [{"id": "draft", "label": tr("Prepare my request", "আবেদনের খসড়া করুন")}]
    if case.kind == "stock":
        return [{"id": "small", "label": tr("Test a smaller batch", "ছোট চালান পরীক্ষা")},
                {"id": "supplier", "label": tr("Ask the supplier", "সরবরাহকারীকে অনুরোধ")},
                {"id": "wait", "label": tr("Wait and review later", "অপেক্ষা করে আবার দেখুন")}]
    if case.kind == "shortfall":
        return [{"id": "collect", "label": tr("Plan customer collections", "বাকি আদায়ের পরিকল্পনা")},
                {"id": "supplier", "label": tr("Ask for more time", "সময় বাড়াতে অনুরোধ")},
                {"id": "wait", "label": tr("Save a follow-up", "পরে দেখার জন্য রাখুন")}]
    return [{"id": "save", "label": tr("Save for review", "পর্যালোচনার জন্য রাখুন")},
            {"id": "supplier", "label": tr("Ask for a complete quote", "সম্পূর্ণ প্রস্তাব চান")},
            {"id": "wait", "label": tr("Wait and review later", "অপেক্ষা করে আবার দেখুন")}]


def view(db, case, today):
    snap = snapshot(db, case.business_id, today)
    qs = questions(case.kind, case.answers, snap)
    pending = [q for q in qs if q["id"] not in case.answers]
    result = case.result if case.status == "completed" else calculate(case, snap) if not pending else None
    docs = list(db.scalars(select(CaseDocument).where(CaseDocument.case_id == case.id)))
    return {"id": case.id, "kind": case.kind, "title": KINDS[case.kind], "status": case.status,
            "version": case.version, "answers": case.answers, "questions": qs,
            "next_question": next_question(case.kind, case.answers, pending), "remaining": len(pending),
            "checkpoint_due": len(case.answers) - case.checkpoint >= 6 and bool(pending),
            "snapshot": snap, "result": result or case.result,
            "stale": case.status == "completed" and case.kind in ("loan", "stock", "shortfall", "paperwork", "strategy")
                     and (case.result.get("fingerprint") != snap["fingerprint"] or case.result.get("evidence_changed", False)),
            "options": options(case, result) if not pending else [],
            "preview": case.preview if case.preview.get("fingerprint") == snap["fingerprint"] else {},
            "documents": [{"id": d.id, "name": d.name, "stage": d.stage, "reference": d.reference,
                           "attachment": d.attachment, "body": None if d.attachment else d.content} for d in docs],
            "updated_at": case.updated_at.isoformat()}


def build_preview(db, case, today, action, text=None):
    snap = snapshot(db, case.business_id, today)
    qs = questions(case.kind, case.answers, snap)
    if any(q["id"] not in case.answers for q in qs):
        fail("finish_questions")
    result = calculate(case, snap)
    if action not in [o["id"] for o in options(case, result)]:
        fail("invalid_action")
    a, lang = case.answers, case.language
    body, destination = "", ""
    if case.kind == "strategy":
        if not a.get("review_date") or a["review_date"] < today.isoformat():
            fail("need_information")
        if action == "save" and result["status"] == "need_information":
            fail("need_information")
        if action == "supplier":
            destination = tr("Your supplier — review the recipient before sharing", "আপনার সরবরাহকারী — শেয়ারের আগে প্রাপক যাচাই করুন")[lang]
            body = tr(
                f"Please provide a dated written quote for {a.get('item') or '[item]'}, quantity {a.get('quantity') or '[quantity]'}. Include delivery, preparation/installation, all charges, payment terms, usable capacity, warranty and product-specific storage conditions and shelf-life evidence. Please quote a smaller quantity and staged delivery too.",
                f"{a.get('item') or '[পণ্য]'}, পরিমাণ {a.get('quantity') or '[পরিমাণ]'}-এর তারিখসহ লিখিত দাম দিন। পরিবহন, প্রস্তুতি/বসানো, সব চার্জ, পেমেন্টের শর্ত, ব্যবহারযোগ্য ধারণক্ষমতা, ওয়ারেন্টি এবং পণ্যের সংরক্ষণ শর্ত ও মেয়াদের প্রমাণ দিন। কম পরিমাণ ও ধাপে ধাপে সরবরাহের দামও দিন।")[lang]
        else:
            destination = tr("Your saved plan — review with your pilot facilitator", "আপনার সেভ করা পরিকল্পনা — পাইলট সহায়তাকারীর সঙ্গে দেখুন")[lang]
            body = tr(
                f"Planning draft: {a.get('item') or '[item]'}\nPurchase date: {a.get('buy_date') or '[unknown]'}\nReview date: {a['review_date']}\n\nDemand evidence: {a.get('evidence') or '[unknown]'}\nStorage plan: {a.get('storage_plan') or '[unknown]'}\nAuthority advice to verify: {a.get('rule_notes') or '[not yet checked]'}\n\nPending quote, storage and local regulatory review. No purchase or legal clearance has been made.",
                f"পরিকল্পনার খসড়া: {a.get('item') or '[পণ্য]'}\nকেনার তারিখ: {a.get('buy_date') or '[অজানা]'}\nপর্যালোচনার তারিখ: {a['review_date']}\n\nচাহিদার প্রমাণ: {a.get('evidence') or '[অজানা]'}\nসংরক্ষণের পরিকল্পনা: {a.get('storage_plan') or '[অজানা]'}\nকর্তৃপক্ষের পরামর্শ যাচাই: {a.get('rule_notes') or '[যাচাই বাকি]'}\n\nদাম, সংরক্ষণ ও স্থানীয় নিয়ম যাচাই বাকি। কেনাকাটা বা আইনি অনুমোদন হয়নি।")[lang]
    if case.kind == "record":
        required = [q["id"] for q in qs if q["id"] not in ("note",)]
        if any(a.get(k) is None for k in required):
            fail("need_information")
        if a.get("interest", 0) > a.get("amount", 0):
            fail("invalid_number")
        if a.get("record_type") == "transfer" and a.get("channel") == a.get("to_channel"):
            fail("different_accounts")
        if a.get("due_date") and a["due_date"] < a["date"]:
            fail("invalid_date")
        if a.get("settled") == "partial" and not 0 < a["paid_now"] < a["amount"]:
            fail("invalid_number")
    elif case.kind == "collect":
        i = result["invoice"]
        if not i or a.get("disputed") is None:
            fail("invoice_unavailable")
        if a.get("disputed") == "yes":
            body = (f"Hello {i['name']}, could we review the bill together and clarify the amount before arranging payment?"
                    if lang == "en" else f"প্রিয় {i['name']}, টাকা দেওয়ার আগে বিলটি একসঙ্গে দেখে পরিমাণ ঠিক করে নিতে চাই।")
        else:
            body = (f"Hello {i['name']}, our records show ৳{i['outstanding']:,.2f} still due. Please check the bill and let us know when you can pay. Thank you."
                    if lang == "en" else f"প্রিয় {i['name']}, আমাদের হিসাবে ৳{i['outstanding']:,.2f} বাকি আছে। বিলটি দেখে কবে দিতে পারবেন জানাবেন। ধন্যবাদ।")
        destination = i["name"]
    elif case.kind == "paperwork":
        if not a.get("topic") or not a.get("request"):
            fail("need_information")
        rule = next(s for s in sources(db, today) if s["id"] == a["topic"])
        destination = rule["destination"][lang]
        if a["topic"] == "trade" and a.get("authority") != "dscc":
            destination = tr("Your issuing local authority; confirm the correct office.", "আপনার স্থানীয় কর্তৃপক্ষ; সঠিক দপ্তর যাচাই করুন।")[lang]
        body = (f"To: {destination}\nSubject: Request for guidance — {rule['title'][lang]}\n\nBusiness: {snap['business']}\nActivity: {a.get('activity') or '[to complete]'}\nPeriod: {a.get('period') or '[to complete]'}\n\n{a['request']}\n\nDocuments available: {a.get('documents') or '[to complete]'}\n\nPlease advise the applicable requirements, prescribed form, fees and submission process.\n\nName and signature: __________________"
                if lang == "en" else f"বরাবর\nসংশ্লিষ্ট কর্মকর্তা\nবিষয়: {rule['title'][lang]} সম্পর্কে সহায়তার আবেদন\n\nব্যবসা: {snap['business']}\nকার্যক্রম: {a.get('activity') or '[পূরণ করুন]'}\nসময়কাল: {a.get('period') or '[পূরণ করুন]'}\n\n{a['request']}\n\nপ্রস্তুত কাগজপত্র: {a.get('documents') or '[পূরণ করুন]'}\n\nপ্রযোজ্য শর্ত, নির্ধারিত ফরম, ফি ও দাখিলের পদ্ধতি জানালে উপকৃত হব।\n\nনাম ও স্বাক্ষর: __________________")
    elif action == "supplier" and case.kind != "strategy":
        destination = tr("Supplier or lender — choose the recipient before sharing", "সরবরাহকারী বা ঋণদাতা — শেয়ারের আগে প্রাপক বাছুন")[lang]
        body = tr("Please send written prices, all charges and payment dates. Could we discuss a smaller order or more time to pay?",
                  "লিখিত দাম, সব চার্জ ও পেমেন্টের তারিখ পাঠাবেন। ছোট অর্ডার বা পেমেন্টের জন্য বাড়তি সময় নিয়ে আলোচনা করতে চাই।")[lang]
    if text is not None and body:
        body = text
    reminder_date = a.get("review_date")
    if case.kind == "paperwork" and a.get("deadline") and a.get("deadline_source"):
        reminder_date = a["deadline"]
    if case.kind == "record" and a.get("due_date"):
        reminder_date = a["due_date"]
    if action == "small" and result["status"] == "need_information":
        fail("need_information")
    quantity = max(1, a.get("quantity", 0) // 2) if action == "small" else None
    budget = money(quantity * a["unit_cost"] + a["delivery"]) if quantity else None
    if quantity and (a["cash"] - budget < a["reserve"] or result["metrics"]["per_item"] <= 0):
        fail("purchase_too_tight")
    return {"action": action, "result": result, "fingerprint": snap["fingerprint"], "body": body,
            "destination": destination, "reminder_date": reminder_date, "test_quantity": quantity,
            "test_budget": budget, "external_delivery": False,
            "title": KINDS[case.kind], "answers": a, "created_on": today.isoformat()}


def commit_action(db, case, preview, today):
    """Caller atomically claims the case first. No commits here: all effects are one transaction."""
    a, bid = case.answers, case.business_id
    effects = {}
    invoice_id = None
    if case.kind == "record" and a["record_type"] != "check":
        t = a["record_type"]
        if a.get("settled") in ("no", "partial"):
            inv = Invoice(business_id=bid, kind="receivable" if t == "sale" else "payable",
                          invoice_no=f"GUIDED-{case.id}", counterparty=a["party"], amount=a["amount"],
                          amount_paid=a.get("paid_now", 0), issue_date=date.fromisoformat(a["date"]), due_date=date.fromisoformat(a["due_date"]),
                          status="partial" if a.get("paid_now") else "open", notes=a["description"], source="guided")
            db.add(inv); db.flush(); invoice_id = inv.id; effects["invoice_id"] = inv.id
            if a.get("paid_now"):
                payment = Transaction(business_id=bid, txn_date=date.fromisoformat(a["date"]), amount=a["paid_now"],
                    direction="in" if t == "sale" else "out", category="sales" if t == "sale" else "stock_purchase",
                    counterparty=a["party"], description=a["description"], channel=a["channel"], source="guided",
                    reference=f"CASE-{case.id}", categorized_by="user", flags=["product_costs_needed"])
                db.add(payment); db.flush()
                db.add(InvoicePayment(business_id=bid, invoice_id=inv.id, amount=a["paid_now"], paid_on=payment.txn_date,
                    channel=a["channel"], transaction_id=payment.id, created_by="guided"))
                effects["transaction_ids"] = [payment.id]
        else:
            cats = {"sale": ("in", "sales"), "purchase": ("out", "stock_purchase"), "expense": ("out", "misc_expense"),
                    "borrow": ("in", "loan_received"), "repay": ("out", "loan_repayment"),
                    "withdraw": ("out", "owner_drawings"), "transfer": ("out", "internal_transfer"),
                    "advance": ("in", "customer_advance"), "refund": ("out", "sales_returns")}
            direction, category = cats[t]
            entries = [(a["amount"], direction, category, a["channel"])]
            if t == "transfer":
                entries.append((a["amount"], "in", "internal_transfer", a["to_channel"]))
            if t == "repay":
                entries = [(a["amount"] - a["interest"], "out", "loan_repayment", a["channel"]),
                           (a["interest"], "out", "loan_interest", a["channel"])]
            ids = []
            for amount, direction, category, channel in entries:
                if amount <= 0:
                    continue
                row = Transaction(business_id=bid, txn_date=date.fromisoformat(a["date"]), amount=amount,
                    direction=direction, category=category, counterparty=a.get("party", ""), description=a["description"],
                    channel=channel, source="guided", reference=f"CASE-{case.id}", categorized_by="user",
                    flags=["product_costs_needed"] if t in ("sale", "purchase", "refund") else [])
                db.add(row); db.flush(); ids.append(row.id)
            effects["transaction_ids"] = ids
    if preview["body"]:
        d = CaseDocument(business_id=bid, case_id=case.id, name=KINDS[case.kind][case.language] + ".txt", content=preview["body"])
        db.add(d); db.flush(); effects["document_id"] = d.id
    reminder = preview["reminder_date"]
    if case.kind == "record" and a["record_type"] == "check" and preview["result"]["status"] == "check_records":
        reminder = today.isoformat()
    if reminder:
        due = date.fromisoformat(reminder)
        alert = Alert(business_id=bid, kind="custom", title=KINDS[case.kind][case.language],
                      message=tr("Open the saved task to continue.", "সেভ করা কাজ খুলে এগিয়ে যান।")[case.language],
                      due_date=due, status="scheduled" if due > today else "open", dedupe_key=f"guided:{case.id}",
                      data={"case_id": case.id, "task_title": KINDS[case.kind],
                            "reconciliation": case.kind == "record" and preview["result"]["status"] == "check_records"}, created_by="user")
        db.add(alert); db.flush()
        db.add(ReminderJob(business_id=bid, case_id=case.id, alert_id=alert.id, due_date=due,
                          invoice_id=invoice_id or (int(a["invoice_id"]) if case.kind == "collect" else None),
                          kind="renewal" if case.kind == "paperwork" else "review" if case.kind == "strategy" else "payment"))
        effects["alert_id"] = alert.id
    case.result = {**preview["result"], "effects": effects, "action": preview["action"],
                   "test_quantity": preview["test_quantity"], "test_budget": preview["test_budget"],
                   "confirmed_on": today.isoformat(), "fingerprint": preview["fingerprint"],
                   "human_review": "pending" if case.kind in ("loan", "paperwork", "strategy") else "not_required"}
    case.status = "completed"
    return effects
