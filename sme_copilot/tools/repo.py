"""Read-side data access: load a business's data as pandas DataFrames for the finance tools."""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.models import Business, Invoice, Obligation, Transaction

TXN_COLUMNS = ["id", "date", "amount", "direction", "category", "counterparty", "description", "channel",
               "source", "source_row", "batch_id", "is_anomaly", "flags"]
INV_COLUMNS = ["id", "kind", "invoice_no", "counterparty", "amount", "amount_paid", "issue_date", "due_date",
               "paid_date", "status", "source", "source_row"]


def empty_txn_df() -> pd.DataFrame:
    df = pd.DataFrame(columns=TXN_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    return df


def load_transactions(session: Session, business_id: int, *, include_duplicates: bool = False,
                      end: date | None = None) -> pd.DataFrame:
    q = select(Transaction).where(Transaction.business_id == business_id)
    if not include_duplicates:
        q = q.where(Transaction.is_duplicate.is_(False))
    if end is not None:
        q = q.where(Transaction.txn_date <= end)
    rows = session.scalars(q.order_by(Transaction.txn_date, Transaction.id)).all()
    if not rows:
        return empty_txn_df()
    df = pd.DataFrame([{
        "id": t.id, "date": t.txn_date, "amount": float(t.amount), "direction": t.direction,
        "category": t.category, "counterparty": t.counterparty or "", "description": t.description or "",
        "channel": t.channel, "source": t.source, "source_row": t.source_row, "batch_id": t.batch_id,
        "is_anomaly": bool(t.is_anomaly), "flags": list(t.flags or []),
    } for t in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_invoices(session: Session, business_id: int) -> pd.DataFrame:
    rows = session.scalars(select(Invoice).where(Invoice.business_id == business_id)).all()
    df = pd.DataFrame([{
        "id": i.id, "kind": i.kind, "invoice_no": i.invoice_no, "counterparty": i.counterparty,
        "amount": float(i.amount), "amount_paid": float(i.amount_paid or 0), "issue_date": i.issue_date,
        "due_date": i.due_date, "paid_date": i.paid_date, "status": i.status, "source": i.source,
        "source_row": i.source_row,
    } for i in rows], columns=INV_COLUMNS)
    for c in ("issue_date", "due_date", "paid_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def load_obligations(session: Session, business_id: int) -> list[Obligation]:
    return list(session.scalars(select(Obligation).where(Obligation.business_id == business_id,
                                                         Obligation.active.is_(True))).all())


def get_business(session: Session, business_id: int) -> Business:
    b = session.get(Business, business_id)
    if b is None:
        raise LookupError(f"business {business_id} not found")
    return b


def cash_position(business: Business, txns: pd.DataFrame, as_of: date) -> tuple[float, dict]:
    """Current liquid balance = opening balance + inflows - outflows since the opening date.

    Returns (balance, breakdown) where breakdown supports the explainability trace.
    """
    start = pd.Timestamp(business.opening_balance_date) if business.opening_balance_date else None
    df = txns[txns["date"] <= pd.Timestamp(as_of)]
    if start is not None:
        df = df[df["date"] > start]
    inflow = float(df.loc[df["direction"] == "in", "amount"].sum())
    outflow = float(df.loc[df["direction"] == "out", "amount"].sum())
    opening = float(business.opening_cash_balance or 0)
    bal = opening + inflow - outflow
    return round(bal, 2), {"opening": opening, "opening_date": str(business.opening_balance_date or ""),
                           "inflow": round(inflow, 2), "outflow": round(outflow, 2), "rows": df["id"].tolist()}
