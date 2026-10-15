"""Bookkeeping basics: customer/supplier balances (baki ledger), invoices with full/partial payments,
P&L / cash-flow / aging reports with CSV and PDF export."""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.db import get_db
from sme_copilot.models import Business, Invoice, InvoiceLine, InvoicePayment, Transaction, User
from sme_copilot.security import audit
from sme_copilot.security.pii import mask_account
from sme_copilot.tools import repo
from sme_copilot.tools.analysis import aging, profitability, resolve_period
from sme_copilot.tools.books_pdf import invoice_pdf, pdf_money, table_pdf
from sme_copilot.tools.categorize import categories
from sme_copilot.tools.ingestion import refresh_anomalies

from .deps import as_of_today, current_user, require_tier

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


def _payments(db: Session, inv: Invoice) -> list[InvoicePayment]:
    return list(db.scalars(select(InvoicePayment).where(InvoicePayment.invoice_id == inv.id)
                           .order_by(InvoicePayment.paid_on, InvoicePayment.id)))


def payment_lines(db: Session, inv: Invoice) -> list[tuple[date, float, str]]:
    """Payments against an invoice. Paid amounts not backed by a payment row (imported invoices) show as one line."""
    rows = [(p.paid_on, float(p.amount), p.channel) for p in _payments(db, inv)]
    rest = round(float(inv.amount_paid or 0) - sum(r[1] for r in rows), 2)
    if rest > 0.005:
        rows.insert(0, (inv.paid_date or inv.issue_date, rest, "recorded on import"))
    return rows


@router.get("/parties/ledger")
def party_ledger(name: str, kind: Literal["customer", "supplier"] = "customer", user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    lines = ledger_entries(db, user.business_id, kind, name)
    if not lines:
        raise HTTPException(404, "no invoices for this party")
    return {"name": name, "kind": kind, "lines": lines, "balance": lines[-1]["balance"]}


# ----------------------------------------------------------------------------- invoices
def display_status(i: Invoice, today: date) -> str:
    """draft | sent | partial | paid | overdue | written_off ('open' is stored for sent invoices)."""
    if i.status in ("draft", "paid", "written_off"):
        return i.status
    if _outstanding(i) > 0.005 and i.due_date < today:
        return "overdue"
    return "partial" if i.status == "partial" else "sent"


def _inv_dict(i: Invoice, today: date) -> dict[str, Any]:
    return {"id": i.id, "kind": i.kind, "invoice_no": i.invoice_no, "counterparty": i.counterparty,
            "phone": mask_account(i.counterparty_phone), "amount": float(i.amount),
            "amount_paid": float(i.amount_paid or 0), "outstanding": _outstanding(i),
            "issue_date": i.issue_date.isoformat(), "due_date": i.due_date.isoformat(),
            "paid_date": i.paid_date.isoformat() if i.paid_date else None, "status": display_status(i, today),
            "days_overdue": max(0, (today - i.due_date).days) if _outstanding(i) > 0.005 else 0,
            "notes": i.notes, "source": i.source}


def _get_invoice(db: Session, user: User, invoice_id: int) -> Invoice:
    i = db.get(Invoice, invoice_id)
    if i is None or i.business_id != user.business_id:
        raise HTTPException(404, "invoice not found")
    return i


class LineIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=200)
    quantity: float = Field(1, gt=0, le=1e7)
    rate: float = Field(..., ge=0, le=1e10)


class InvoiceIn(BaseModel):
    kind: Literal["receivable", "payable"] = "receivable"
    counterparty: str = Field(..., min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=30)
    invoice_no: str = Field("", max_length=60)
    issue_date: date | None = None
    due_date: date | None = None
    lines: list[LineIn] = Field(..., min_length=1, max_length=50)
    notes: str = Field("", max_length=1000)
    send: bool = False  # False keeps it as a draft


class PaymentIn(BaseModel):
    amount: float = Field(..., gt=0, le=1e10)
    paid_on: date | None = None
    channel: Literal["cash", "bank", "bkash", "nagad", "rocket", "card"] = "cash"


@router.get("/invoices")
def list_invoices(kind: str = "", status: str = "", user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    today = as_of_today()
    q = select(Invoice).where(Invoice.business_id == user.business_id)
    if kind:
        q = q.where(Invoice.kind == kind)
    rows = [_inv_dict(i, today) for i in db.scalars(q.order_by(Invoice.issue_date.desc(), Invoice.id.desc()))]
    return [r for r in rows if r["status"] == status] if status else rows


def next_invoice_no(db: Session, business_id: int, kind: str) -> str:
    existing = {n for (n,) in db.execute(select(Invoice.invoice_no).where(Invoice.business_id == business_id))}
    prefix, n = ("INV" if kind == "receivable" else "BILL"), len(existing) + 1
    while f"{prefix}-{n:04d}" in existing:
        n += 1
    return f"{prefix}-{n:04d}"


def add_invoice(db: Session, user: User, body: InvoiceIn, *, source: str = "manual") -> Invoice:
    """Create an invoice with its lines (no commit, no audit: callers do both)."""
    issue = body.issue_date or as_of_today()
    due = body.due_date or issue + timedelta(days=30)
    if due < issue:
        raise HTTPException(422, "due date is before the invoice date")
    no = body.invoice_no.strip()
    if no and db.scalar(select(Invoice.id).where(Invoice.business_id == user.business_id, Invoice.invoice_no == no)):
        raise HTTPException(409, "invoice number already used")
    no = no or next_invoice_no(db, user.business_id, body.kind)
    total = round(sum(ln.quantity * ln.rate for ln in body.lines), 2)
    if total <= 0:
        raise HTTPException(422, "invoice total must be more than zero")
    inv = Invoice(business_id=user.business_id, kind=body.kind, invoice_no=no, counterparty=body.counterparty.strip(),
                  counterparty_phone=body.phone or None, amount=total, amount_paid=0, issue_date=issue, due_date=due,
                  status="open" if body.send else "draft", notes=body.notes, source=source)
    db.add(inv)
    db.flush()
    db.add_all([InvoiceLine(invoice_id=inv.id, **ln.model_dump()) for ln in body.lines])
    return inv


@router.post("/invoices")
def create_invoice(body: InvoiceIn, user: User = Depends(require_tier(1)),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    inv = add_invoice(db, user, body)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="create_invoice", tier=1, inputs=body.model_dump(mode="json"),
                 result={"invoice_id": inv.id, "invoice_no": inv.invoice_no, "amount": float(inv.amount)},
                 commit=False)
    db.commit()
    return _inv_dict(inv, as_of_today())


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    i = _get_invoice(db, user, invoice_id)
    lines = db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == i.id).order_by(InvoiceLine.id)).all()
    fallback = [{"description": i.notes or f"Invoice {i.invoice_no}", "quantity": 1, "rate": float(i.amount)}]
    return {**_inv_dict(i, as_of_today()),
            "lines": [{"description": ln.description, "quantity": ln.quantity, "rate": float(ln.rate)}
                      for ln in lines] or fallback,
            "payments": [{"date": d.isoformat(), "amount": a, "channel": c} for d, a, c in payment_lines(db, i)]}


@router.post("/invoices/{invoice_id}/send")
def send_invoice(invoice_id: int, user: User = Depends(require_tier(1)),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    """Mark a draft as sent (nothing is transmitted; the owner shares the PDF)."""
    i = _get_invoice(db, user, invoice_id)
    if i.status != "draft":
        raise HTTPException(409, "only drafts can be marked as sent")
    i.status = "open"
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="send_invoice", tier=1, inputs={"invoice_id": i.id}, result={"status": "sent"}, commit=False)
    db.commit()
    return _inv_dict(i, as_of_today())


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf_download(invoice_id: int, user: User = Depends(current_user),
                         db: Session = Depends(get_db)) -> Response:
    d = get_invoice(invoice_id, user, db)
    b = db.get(Business, user.business_id)
    pdf = invoice_pdf(business={"name": b.name, "district": b.district}, invoice=d, lines=d["lines"],
                      payments=d["payments"], style=(b.prefs or {}).get("number_style", "lakh"))
    fname = "".join(c for c in d["invoice_no"] if c.isalnum() or c in "-_") or str(invoice_id)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="invoice_{fname}.pdf"'})


@router.post("/invoices/{invoice_id}/payments")
def record_payment(invoice_id: int, body: PaymentIn, user: User = Depends(require_tier(1)),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    """Record a full or partial payment that already happened (bookkeeping only; no money is moved).
    Creates the matching cash transaction so cash balance and reports stay in step."""
    i = _get_invoice(db, user, invoice_id)
    if i.status in ("draft", "written_off"):
        raise HTTPException(409, f"cannot record a payment on a {i.status} invoice")
    owed = _outstanding(i)
    if owed <= 0.005:
        raise HTTPException(409, "invoice is already fully paid")
    if body.amount > owed + 0.005:
        raise HTTPException(422, f"amount is more than the balance due ({owed:.2f})")
    paid_on = body.paid_on or as_of_today()
    rec = i.kind == "receivable"
    t = Transaction(business_id=user.business_id, txn_date=paid_on, amount=body.amount,
                    direction="in" if rec else "out", category="sales" if rec else "inventory",
                    counterparty=i.counterparty, description=f"Payment for {i.invoice_no or 'invoice #' + str(i.id)}",
                    channel=body.channel, reference=i.invoice_no, source="manual", categorized_by="user")
    db.add(t)
    db.flush()
    p = InvoicePayment(business_id=user.business_id, invoice_id=i.id, amount=body.amount, paid_on=paid_on,
                       channel=body.channel, transaction_id=t.id, created_by=user.username)
    db.add(p)
    i.amount_paid = round(float(i.amount_paid or 0) + body.amount, 2)
    if _outstanding(i) <= 0.005:
        i.status, i.paid_date = "paid", paid_on
    else:
        i.status = "partial"
    db.flush()
    refresh_anomalies(db, user.business_id)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="record_invoice_payment", tier=1, inputs={"invoice_id": i.id, **body.model_dump(mode="json")},
                 result={"payment_id": p.id, "transaction_id": t.id, "status": i.status,
                         "outstanding": _outstanding(i)}, commit=False)
    db.commit()
    return {**_inv_dict(i, as_of_today()), "payment_id": p.id, "transaction_id": t.id}


# ----------------------------------------------------------------------------- reports
def report_period(period: str, start: date | None, end: date | None, today: date) -> tuple[date, date, str]:
    """month | quarter | year (to date) | custom (start+end) | any named period the analysis tools accept."""
    if period == "custom":
        if not (start and end) or end < start:
            raise HTTPException(422, "custom period needs a start and end date (start before end)")
        return start, end, f"{start.isoformat()} to {end.isoformat()}"
    if period == "quarter":
        s = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        return s, today, f"Q{(today.month - 1) // 3 + 1} {today.year} (to date)"
    if period == "year":
        return date(today.year, 1, 1), today, f"{today.year} (to date)"
    try:
        return resolve_period("this_month" if period == "month" else period, today)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _behavior(cat: str) -> str:
    return (categories().get(cat) or {}).get("behavior", "variable")


def _cat_totals(df, direction: str) -> dict[str, float]:
    if df.empty:
        return {}
    g = df[df["direction"] == direction].groupby("category")["amount"].sum()
    return {k: round(float(v), 2) for k, v in sorted(g.items(), key=lambda kv: -kv[1])}


def build_report(db: Session, b: Business, kind: str, start: date, end: date, label: str, today: date,
                 party_kind: str = "receivable") -> dict[str, Any]:
    nice = lambda c: c.replace("_", " ").capitalize()  # noqa: E731
    if kind == "aging":
        inv = repo.load_invoices(db, b.id)
        ag = aging(inv, today, party_kind) if not inv.empty else None
        cols = ["Not yet due", "0-30 days", "31-60 days", "61+ days"]
        per: dict[str, list[float]] = {}
        for it in (ag.items if ag else []):
            d = it.days_past_due
            idx = 0 if d <= 0 else 1 if d <= 30 else 2 if d <= 60 else 3
            per.setdefault(it.counterparty, [0.0] * 4)[idx] += it.outstanding
        rows = [[name, *[round(x, 2) for x in v], round(sum(v), 2)] for name, v in
                sorted(per.items(), key=lambda kv: -sum(kv[1]))]
        tot = [round(sum(r[i] for r in rows), 2) for i in range(1, 6)]
        who = "Customers" if party_kind == "receivable" else "Suppliers"
        return {"kind": kind, "title": f"{'Receivables' if party_kind == 'receivable' else 'Payables'} aging",
                "period": f"as of {today.isoformat()}", "header": [who, *cols, "Total"],
                "rows": [*rows, ["Total", *tot]], "money_cols": [1, 2, 3, 4, 5], "bold_rows": [len(rows)],
                "chart": dict(zip(cols, tot[:4])), "notes": ["Days are counted past the due date."]}
    txns = repo.load_transactions(db, b.id, end=end)
    df = txns[(txns["date"] >= pd.Timestamp(start)) & (txns["date"] <= pd.Timestamp(end))] if not txns.empty else txns
    if kind == "pnl":
        p = profitability(txns, start, end, label)
        outs = _cat_totals(df, "out")
        opex = [[f"  {nice(c)}", -v] for c, v in outs.items() if _behavior(c) in ("variable", "fixed")]
        rows = [["Sales (revenue)", p.revenue], ["Cost of goods (stock purchases)", -p.cogs],
                ["Gross profit", p.gross_profit], ["Operating expenses", -(p.variable_opex + p.fixed_opex)], *opex,
                ["Other income", p.other_income], ["Operating profit", p.operating_profit]]
        bold = [2, len(rows) - 1]
        notes = [f"Gross margin {p.gross_margin_pct}% · operating margin {p.net_margin_pct}%"
                 if p.gross_margin_pct is not None else "No sales in this period.",
                 "Cash basis. Not counted in profit: " + (", ".join(
                     f"{k.replace('_', ' ')} {v:,.0f}" for k, v in p.excluded.items() if v) or "none")]
        return {"kind": kind, "title": "Profit & loss", "period": label, "header": ["Line", "Amount"], "rows": rows,
                "money_cols": [1], "bold_rows": bold, "notes": notes}
    if kind == "cashflow":
        opening, _ = repo.cash_position(b, txns, start - timedelta(days=1))
        closing, _ = repo.cash_position(b, txns, end)
        ins, outs = _cat_totals(df, "in"), _cat_totals(df, "out")
        rows = [["Opening cash", opening], ["Money in", sum(ins.values())],
                *[[f"  {nice(c)}", v] for c, v in ins.items()], ["Money out", -sum(outs.values())],
                *[[f"  {nice(c)}", -v] for c, v in outs.items()],
                ["Net cash flow", round(sum(ins.values()) - sum(outs.values()), 2)], ["Closing cash", closing]]
        bold = [0, 1, 2 + len(ins), len(rows) - 2, len(rows) - 1]
        return {"kind": kind, "title": "Cash flow", "period": label, "header": ["Line", "Amount"],
                "rows": [[r[0], round(float(r[1]), 2)] for r in rows], "money_cols": [1], "bold_rows": bold,
                "notes": ["Opening and closing cash = opening balance + all recorded money in - money out."]}
    raise HTTPException(404, "unknown report")


@router.get("/reports/{kind}")
def report(kind: Literal["pnl", "cashflow", "aging"], period: str = "month", start: date | None = None,
           end: date | None = None, party: Literal["receivable", "payable"] = "receivable",
           fmt: Literal["json", "csv", "pdf"] = "json", user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    today = as_of_today()
    s, e, label = report_period(period, start, end, today)
    b = db.get(Business, user.business_id)
    r = build_report(db, b, kind, s, e, label, today, party)
    r.update(start=s.isoformat(), end=e.isoformat())
    if fmt == "json":
        return r
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="data",
                 action="export_report", inputs={"kind": kind, "period": label, "fmt": fmt})
    fname = f"{kind}_{s.isoformat()}_{e.isoformat()}.{fmt}"
    disp = {"Content-Disposition": f'attachment; filename="{fname}"'}
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([r["title"], r["period"]])
        w.writerow(r["header"])
        w.writerows([[_csv_safe(c) for c in row] for row in r["rows"]])
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=disp)
    style = (b.prefs or {}).get("number_style", "lakh")
    rows = [[pdf_money(c, style) if i in r["money_cols"] else c for i, c in enumerate(row)] for row in r["rows"]]
    pdf = table_pdf(f"{r['title']} - {b.name}", r["period"], r["header"], rows,
                    right_cols=tuple(r["money_cols"]), notes=r["notes"])
    return Response(pdf, media_type="application/pdf", headers=disp)


def _csv_safe(v: Any) -> Any:
    """Stop spreadsheet formula injection from names in imported files."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v
