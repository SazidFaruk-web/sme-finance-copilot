"""Quick entries that change what customers owe, not just cash.

* A credit sale ("Rahman Mobile baki 6000", "sold chargers 6000 on credit to Rahman") creates an open customer bill:
  no cash moved, so no transaction; the customer now owes the amount.
* A payment from a customer who has open bills ("received 18600 from Agrabad Phone Point", "Masud bhai 1000 dilo")
  settles those bills oldest first and records the cash, like recording a payment on the bill itself. Without this the
  payment was a second sale and the bill stayed overdue (found in the 2026-10-19 persona test).

The caller asks the owner to confirm before either is saved. Only deterministic code reads names and amounts.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.models import Invoice, InvoicePayment, Transaction
from sme_copilot.tools.textnorm import bn_to_ascii_digits
from sme_copilot.tools.nl_entry import money_amount

CREDIT_WORDS = r"(?:baki|bakite|বাকিতে|বাকি|on credit|credit sale|udhar|udhaar|উধার)"
PAID_WORDS = re.compile(r"\b(?:received|got|paid me|collected|dilo|dilen|diyeche|pelam|joma)\b|দিল|দিয়েছে|দিলেন|পেলাম|জমা", re.I)
FILLER = re.compile(r"\b(?:sold|sale|bikri|to|for|from|the|tk|taka|cash|bkash|nagad|bank|৳)\b|বিক্রি|টাকা", re.I)
CREDIT_DAYS = 30


def _amount(text: str) -> float | None:
    amount = money_amount(text)
    return amount if amount is not None and amount > 0 else None


def _clean_name(s: str) -> str:
    s = re.sub(r"\d[\d,.]*", " ", bn_to_ascii_digits(s))
    s = FILLER.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" -,.:")[:120]


def credit_sale(text: str) -> tuple[str, float] | None:
    """(customer, amount) when the entry says goods went out on credit, else None."""
    m = re.search(CREDIT_WORDS, text, re.I)
    if not m or PAID_WORDS.search(text):
        return None
    amount = _amount(text)
    before = _clean_name(text[:m.start()])
    after = re.search(r"\bto\s+(.+?)(?:\s+for\b|$)", text[m.end():], re.I) or re.search(r"\bto\s+(.+?)(?:\s+for\b|$)", text, re.I)
    name = (_clean_name(after.group(1)) if after else "") or before  # "... on credit to Rahman" names the customer
    return (name, amount) if name and amount else None


def open_receivables(session: Session, business_id: int) -> list[Invoice]:
    return list(session.scalars(select(Invoice).where(Invoice.business_id == business_id, Invoice.kind == "receivable",
                                                      Invoice.status.in_(("open", "partial")))
                                .order_by(Invoice.due_date, Invoice.id)))


def _owed(i: Invoice) -> float:
    return round(float(i.amount) - float(i.amount_paid or 0), 2)


def customer_payment(session: Session, business_id: int, text: str) -> tuple[str, float, list[Invoice]] | None:
    """(customer, amount, their open bills oldest first) when a known customer with open bills paid, else None."""
    if not PAID_WORDS.search(text):
        return None
    amount = _amount(text)
    if not amount:
        return None
    low = text.lower()
    bills: dict[str, list[Invoice]] = {}
    for i in open_receivables(session, business_id):
        name = (i.counterparty or "").strip()
        first = name.split()[0].lower() if name else ""
        if name and (name.lower() in low or (len(first) >= 4 and re.search(r"\b" + re.escape(first) + r"\b", low))):
            bills.setdefault(name, []).append(i)
    if len(bills) != 1:  # nobody, or ambiguous: treat it as an ordinary entry
        return None
    name, invs = next(iter(bills.items()))
    if amount > sum(_owed(i) for i in invs) + 0.005:  # more than they owe: not (only) a bill payment
        return None
    return name, amount, invs


def record_credit_sale(session: Session, business_id: int, customer: str, amount: float, today: date, note: str) -> Invoice:
    existing = {n for (n,) in session.execute(select(Invoice.invoice_no).where(Invoice.business_id == business_id))}
    n = len(existing) + 1
    while f"CR-{n:04d}" in existing:
        n += 1
    inv = Invoice(business_id=business_id, kind="receivable", invoice_no=f"CR-{n:04d}", counterparty=customer, amount=amount,
                  amount_paid=0, issue_date=today, due_date=today + timedelta(days=CREDIT_DAYS), status="open",
                  notes=f"Credit sale: {note}"[:1000], source="nl")
    session.add(inv)
    session.flush()
    return inv


def apply_payment(session: Session, business_id: int, invs: list[Invoice], amount: float, today: date, channel: str,
                  actor: str) -> tuple[Transaction, list[dict[str, Any]]]:
    """One cash-in transaction for the payment, spread over the bills oldest first."""
    t = Transaction(business_id=business_id, txn_date=today, amount=amount, direction="in", category="sales",
                    counterparty=invs[0].counterparty, description=f"Payment from {invs[0].counterparty}",
                    channel=channel if channel in ("cash", "bank", "bkash", "nagad", "rocket") else "cash",
                    reference=invs[0].invoice_no, source="nl", categorized_by="user")
    session.add(t)
    session.flush()
    left, applied = amount, []
    for i in invs:
        if left <= 0.005:
            break
        part = round(min(left, _owed(i)), 2)
        session.add(InvoicePayment(business_id=business_id, invoice_id=i.id, amount=part, paid_on=today, channel=t.channel,
                                   transaction_id=t.id, created_by=actor))
        i.amount_paid = round(float(i.amount_paid or 0) + part, 2)
        i.status, i.paid_date = ("paid", today) if _owed(i) <= 0.005 else ("partial", i.paid_date)
        applied.append({"invoice_no": i.invoice_no, "paid": part, "still_owed": max(0.0, _owed(i))})
        left = round(left - part, 2)
    session.flush()
    return t, applied
