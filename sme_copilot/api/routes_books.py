"""Bookkeeping basics: customer/supplier balances (baki ledger), invoices with full/partial payments,
P&L / cash-flow / aging reports with CSV and PDF export, transaction delete with undo,
recurring expenses (rent, salary) and recurring invoices."""
from __future__ import annotations

import calendar
import csv
import io
from datetime import date, datetime, timedelta
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.db import get_db
from sme_copilot.models import (
    Business,
    DeletedTransaction,
    ImportBatch,
    Invoice,
    InvoiceLine,
    InvoicePayment,
    Item,
    Obligation,
    RecurringInvoice,
    StockMovement,
    Transaction,
    User,
)
from sme_copilot.security import audit
from sme_copilot.security.pii import mask_account
from sme_copilot.tools import repo, stock
from sme_copilot.tools.analysis import add_months, aging, profitability, resolve_period
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


# ----------------------------------------------------------------------------- delete with undo
TXN_FIELDS = ("txn_date", "amount", "direction", "category", "counterparty", "description", "channel", "reference",
              "quantity", "item", "source", "batch_id", "source_row", "is_duplicate", "duplicate_of", "is_anomaly",
              "anomaly_reason", "flags", "categorized_by", "category_confidence", "created_at")


def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, (date, datetime)) else v


@router.delete("/transactions/{txn_id}")
def delete_transaction(txn_id: int, user: User = Depends(require_tier(1)),
                       db: Session = Depends(get_db)) -> dict[str, Any]:
    """Delete any transaction into a restorable trash (the UI offers Undo)."""
    t = db.get(Transaction, txn_id)
    if t is None or t.business_id != user.business_id:
        raise HTTPException(404, "transaction not found")
    if db.scalar(select(InvoicePayment.id).where(InvoicePayment.transaction_id == t.id)):
        raise HTTPException(409, "this row is an invoice payment; it cannot be deleted here")
    first = db.scalar(select(StockMovement).where(StockMovement.transaction_id == t.id).order_by(StockMovement.id))
    trash = DeletedTransaction(business_id=user.business_id, original_id=t.id, account_ref=t.account_ref,
                               data={f: _jsonable(getattr(t, f)) for f in TXN_FIELDS},
                               item_id=first.item_id if first else None, deleted_by=user.username)
    db.add(trash)
    stock.reverse_for_transaction(db, t.id)
    db.delete(t)
    db.flush()
    refresh_anomalies(db, user.business_id)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="delete_transaction", tier=1, inputs={"id": txn_id},
                 result={"trash_id": trash.id, "amount": trash.data["amount"], "date": trash.data["txn_date"]},
                 commit=False)
    db.commit()
    return {"deleted": txn_id, "trash_id": trash.id}


@router.post("/transactions/restore/{trash_id}")
def restore_transaction(trash_id: int, user: User = Depends(require_tier(1)),
                        db: Session = Depends(get_db)) -> dict[str, Any]:
    tr = db.get(DeletedTransaction, trash_id)
    if tr is None or tr.business_id != user.business_id:
        raise HTTPException(404, "nothing to restore")
    d = dict(tr.data)
    d["txn_date"] = date.fromisoformat(d["txn_date"])
    d["created_at"] = datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None
    if d.get("batch_id") and db.get(ImportBatch, d["batch_id"]) is None:
        d["batch_id"] = None
    t = Transaction(business_id=user.business_id, account_ref=tr.account_ref,
                    **{k: v for k, v in d.items() if k in TXN_FIELDS and v is not None})
    db.add(t)
    db.flush()
    it = db.get(Item, tr.item_id) if tr.item_id else None
    rtype = stock.txn_type(t)
    if it is not None and it.business_id == user.business_id and rtype and t.quantity and t.quantity > 0:
        stock.add_movement(db, it, stock.MOVE_SIGN[rtype] * t.quantity, rtype, t.id)
    db.delete(tr)
    db.flush()
    refresh_anomalies(db, user.business_id)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="restore_transaction", tier=1, inputs={"trash_id": trash_id},
                 result={"original_id": tr.original_id, "new_id": t.id}, commit=False)
    db.commit()
    return {"restored": t.id, "original_id": tr.original_id}


# ----------------------------------------------------------------------------- recurring items
FREQ_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
MAX_CATCH_UP = 24  # never post more than two years of missed items in one go


def advance(d: date, frequency: str, day: int) -> date | None:
    """Next due date, keeping the chosen day of month (clipped to short months). None for one-off items."""
    if frequency not in FREQ_MONTHS:
        return None
    n = add_months(d.replace(day=1), FREQ_MONTHS[frequency])
    return n.replace(day=min(day, calendar.monthrange(n.year, n.month)[1]))


class RecurringIn(BaseModel):
    type: Literal["expense", "invoice"] = "expense"
    name: str = Field(..., min_length=1, max_length=120)  # what it is (expense) or customer name (invoice)
    category: str = Field("rent", max_length=40)  # expenses only
    description: str = Field("", max_length=200)  # invoice line text
    amount: float = Field(..., gt=0, le=1e9)
    frequency: Literal["monthly", "quarterly", "yearly"] = "monthly"
    next_due: date
    due_days: int = Field(30, ge=0, le=365)  # invoices only


def _rec_dict(o: Obligation | RecurringInvoice) -> dict[str, Any]:
    if isinstance(o, Obligation):
        return {"type": "expense", "id": o.id, "name": o.name, "category": o.category, "amount": float(o.amount),
                "frequency": o.frequency, "next_due": o.next_due.isoformat(), "active": o.active}
    return {"type": "invoice", "id": o.id, "name": o.counterparty, "description": o.description,
            "amount": float(o.amount), "frequency": o.frequency, "next_due": o.next_issue.isoformat(),
            "due_days": o.due_days, "active": o.active}


@router.get("/recurring")
def list_recurring(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    today = as_of_today()
    obl = db.scalars(select(Obligation).where(Obligation.business_id == user.business_id)
                     .order_by(Obligation.next_due)).all()
    ri = db.scalars(select(RecurringInvoice).where(RecurringInvoice.business_id == user.business_id)
                    .order_by(RecurringInvoice.next_issue)).all()
    rows = [_rec_dict(o) for o in [*obl, *ri]]
    for r in rows:
        r["due_now"] = r["active"] and r["next_due"] <= today.isoformat()
    return {"rows": rows, "due_count": sum(r["due_now"] for r in rows)}


@router.post("/recurring")
def create_recurring(body: RecurringIn, user: User = Depends(require_tier(1)),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.type == "expense":
        info = categories().get(body.category)
        if not info or info.get("direction") != "out":
            raise HTTPException(422, "category must be a money-out category")
        o: Obligation | RecurringInvoice = Obligation(
            business_id=user.business_id, name=body.name, category=body.category, amount=body.amount,
            frequency=body.frequency, day_of_month=body.next_due.day, next_due=body.next_due, source="user")
    else:
        o = RecurringInvoice(business_id=user.business_id, counterparty=body.name,
                             description=body.description or body.name, amount=body.amount, frequency=body.frequency,
                             day_of_month=body.next_due.day, next_issue=body.next_due, due_days=body.due_days)
    db.add(o)
    db.flush()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="create_recurring", tier=1, inputs=body.model_dump(mode="json"), result={"id": o.id},
                 commit=False)
    db.commit()
    return _rec_dict(o)


@router.post("/recurring/{rtype}/{rec_id}/stop")
def stop_recurring(rtype: Literal["expense", "invoice"], rec_id: int, user: User = Depends(require_tier(1)),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    o = db.get(Obligation if rtype == "expense" else RecurringInvoice, rec_id)
    if o is None or o.business_id != user.business_id:
        raise HTTPException(404, "recurring item not found")
    o.active = False
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="stop_recurring", tier=1, inputs={"type": rtype, "id": rec_id}, commit=False)
    db.commit()
    return _rec_dict(o)


@router.post("/recurring/post-due")
def post_due(user: User = Depends(require_tier(1)), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Turn every recurring item that is due (on or before today) into a real record, then move it to its next
    date: expenses become money-out transactions, recurring invoices become draft invoices to review and send."""
    today = as_of_today()
    txn_ids: list[int] = []
    inv_ids: list[int] = []
    for o in db.scalars(select(Obligation).where(Obligation.business_id == user.business_id,
                                                 Obligation.active.is_(True), Obligation.next_due <= today)):
        for _ in range(MAX_CATCH_UP):
            t = Transaction(business_id=user.business_id, txn_date=o.next_due, amount=o.amount, direction="out",
                            category=o.category if o.category in categories() else "misc_expense",
                            description=o.name, reference=f"REC-{o.id}", source="recurring", categorized_by="user")
            db.add(t)
            db.flush()
            txn_ids.append(t.id)
            nxt = advance(o.next_due, o.frequency, o.day_of_month)
            if nxt is None:
                o.active = False
                break
            o.next_due = nxt
            if nxt > today:
                break
    for r in db.scalars(select(RecurringInvoice).where(RecurringInvoice.business_id == user.business_id,
                                                       RecurringInvoice.active.is_(True),
                                                       RecurringInvoice.next_issue <= today)):
        for _ in range(MAX_CATCH_UP):
            body = InvoiceIn(counterparty=r.counterparty, issue_date=r.next_issue,
                             due_date=r.next_issue + timedelta(days=r.due_days), notes=f"Recurring ({r.frequency})",
                             lines=[LineIn(description=r.description, quantity=1, rate=float(r.amount))])
            inv_ids.append(add_invoice(db, user, body, source="recurring").id)
            r.next_issue = advance(r.next_issue, r.frequency, r.day_of_month)
            if r.next_issue > today:
                break
    if txn_ids:
        refresh_anomalies(db, user.business_id)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="post_recurring", tier=1, result={"transactions": txn_ids, "invoices": inv_ids}, commit=False)
    db.commit()
    return {"transactions": len(txn_ids), "invoices": len(inv_ids), "transaction_ids": txn_ids, "invoice_ids": inv_ids}
