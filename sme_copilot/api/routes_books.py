"""Bookkeeping basics: customer/supplier balances (baki ledger)."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.db import get_db
from sme_copilot.models import Invoice, User

from .deps import as_of_today, current_user

router = APIRouter(prefix="/api/books")
PARTY_KIND = {"customer": "receivable", "supplier": "payable"}


def _outstanding(i: Invoice) -> float:
    return round(float(i.amount) - float(i.amount_paid or 0), 2)


def _counted(i: Invoice) -> bool:
    """Drafts and written-off invoices do not create a balance owed."""
    return i.status not in ("draft", "written_off")


@router.get("/parties")
def parties(kind: Literal["customer", "supplier"] = "customer", user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    today = as_of_today()
    out: dict[str, dict[str, Any]] = {}
    for i in db.scalars(select(Invoice).where(Invoice.business_id == user.business_id,
                                              Invoice.kind == PARTY_KIND[kind])):
        if not _counted(i):
            continue
        p = out.setdefault(i.counterparty.strip().lower(), {"name": i.counterparty, "invoiced": 0.0, "paid": 0.0,
                                                            "balance": 0.0, "overdue": 0.0, "invoices": 0,
                                                            "last_date": None})
        owed = _outstanding(i)
        p["invoiced"] += float(i.amount)
        p["paid"] += float(i.amount_paid or 0)
        p["balance"] += owed
        p["invoices"] += 1
        if owed > 0.005 and i.due_date < today:
            p["overdue"] += owed
        last = (i.paid_date or i.issue_date).isoformat()
        p["last_date"] = max(p["last_date"] or last, last)
    rows = sorted(out.values(), key=lambda p: -p["balance"])
    for p in rows:
        for k in ("invoiced", "paid", "balance", "overdue"):
            p[k] = round(p[k], 2)
    return {"kind": kind, "as_of": today.isoformat(), "rows": rows,
            "total_balance": round(sum(p["balance"] for p in rows), 2),
            "total_overdue": round(sum(p["overdue"] for p in rows), 2)}


def ledger_entries(db: Session, business_id: int, kind: str, name: str) -> list[dict[str, Any]]:
    """Statement lines for one party: invoices raise the balance, payments lower it (running balance)."""
    invs = [i for i in db.scalars(select(Invoice).where(Invoice.business_id == business_id,
                                                         Invoice.kind == PARTY_KIND[kind]))
            if i.counterparty.strip().lower() == name.strip().lower() and _counted(i)]
    lines: list[tuple[date, int, dict[str, Any]]] = []
    for i in invs:
        ref = i.invoice_no or f"#{i.id}"
        lines.append((i.issue_date, 0, {"date": i.issue_date.isoformat(), "type": "invoice", "ref": ref,
                                        "invoice_id": i.id, "debit": float(i.amount), "credit": 0.0}))
        for d, amt, note in payment_lines(db, i):
            lines.append((d, 1, {"date": d.isoformat(), "type": "payment", "ref": ref, "invoice_id": i.id,
                                 "debit": 0.0, "credit": amt, "note": note}))
    lines.sort(key=lambda x: (x[0], x[1]))
    bal, out = 0.0, []
    for _, _, e in lines:
        bal = round(bal + e["debit"] - e["credit"], 2)
        out.append({**e, "balance": bal})
    return out


def payment_lines(db: Session, inv: Invoice) -> list[tuple[date, float, str]]:
    """Payments against an invoice. Imported invoices only carry amount_paid, shown as one line."""
    paid = float(inv.amount_paid or 0)
    return [(inv.paid_date or inv.issue_date, round(paid, 2), "recorded on import")] if paid > 0.005 else []


@router.get("/parties/ledger")
def party_ledger(name: str, kind: Literal["customer", "supplier"] = "customer", user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    lines = ledger_entries(db, user.business_id, kind, name)
    if not lines:
        raise HTTPException(404, "no invoices for this party")
    return {"name": name, "kind": kind, "lines": lines, "balance": lines[-1]["balance"]}
