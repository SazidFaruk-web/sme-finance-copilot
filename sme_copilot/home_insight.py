"""The short, occasional note under Home's two cards (owner decision 2026-10-19).

Each candidate is something unusual in the owner's own records: a bill that is overdue, spending above money in,
a lot of money still owed by customers, or sales well up or down on last month. Every number is calculated here from
recorded data; the browser only words it (English, Bangla, Chinese) and decides when to show it (about one app open
in ten, for 10 seconds, at most 3 times per note). With nothing unusual, the browser shows a business tip instead.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from sme_copilot.tools import repo
from sme_copilot.tools.analysis import add_months, aging, month_start, profitability

MIN_AMOUNT = 1000  # below this, a gap or a change is not worth interrupting for
GROWTH_PCT = 20
DROP_PCT = 30


def _sum(df, start: date, end: date, direction: str) -> float:
    if df.empty:
        return 0.0
    d = df[(df["date"] >= str(start)) & (df["date"] <= str(end)) & (df["direction"] == direction)]
    return float(d["amount"].sum())


def candidates(session: Session, business_id: int, today: date) -> list[dict[str, Any]]:
    """Most important first. ``id`` is stable for the same fact in the same month, so the browser can count views."""
    out: list[dict[str, Any]] = []
    ym = today.strftime("%Y-%m")

    txns = repo.load_transactions(session, business_id, end=today)

    def paid(o) -> bool:  # a recorded payment of about the same amount and kind since shortly before the due date
        if txns.empty:
            return False
        near = txns[(txns["direction"] == "out") & (txns["date"] >= str(o.next_due - timedelta(days=10)))]
        same = near[(near["category"] == o.category) | near["description"].str.lower().str.contains(o.name.lower().split()[0], regex=False)]
        return bool(((same["amount"] - float(o.amount)).abs() <= 0.2 * float(o.amount)).any())

    for o in sorted(repo.load_obligations(session, business_id), key=lambda o: o.next_due):
        if o.next_due < today and paid(o):
            continue
        if o.next_due < today:
            months = max(1, (today.year - o.next_due.year) * 12 + today.month - o.next_due.month)
            out.append({"id": f"bill_overdue:{o.id}:{o.next_due}", "kind": "warn", "key": "bill_overdue",
                        "params": {"name": o.name, "amount": float(o.amount), "due": str(o.next_due), "months": months}})
        elif o.next_due <= today + timedelta(days=3):
            out.append({"id": f"bill_soon:{o.id}:{o.next_due}", "kind": "reminder", "key": "bill_soon",
                        "params": {"name": o.name, "amount": float(o.amount), "due": str(o.next_due)}})

    start = month_start(today)
    money_in, money_out = _sum(txns, start, today, "in"), _sum(txns, start, today, "out")
    if money_out > money_in and money_out - money_in >= MIN_AMOUNT:
        out.append({"id": f"overspend:{ym}", "kind": "warn", "key": "overspend",
                    "params": {"in": round(money_in, 2), "out": round(money_out, 2), "gap": round(money_out - money_in, 2)}})

    inv = repo.load_invoices(session, business_id)
    if not inv.empty:  # the same late total as the dashboard's "Customers owe you (late)"
        owed = float(aging(inv, today, "receivable", txns).overdue_total)
        if owed >= MIN_AMOUNT and owed > max(money_in, MIN_AMOUNT):
            out.append({"id": f"owed:{ym}", "kind": "warn", "key": "owed", "params": {"owed": round(owed, 2), "in": round(money_in, 2)}})

    # Sales so far this month against the same days of last month.
    prev_start = add_months(start, -1)
    prev_end = min(prev_start + (today - start), start - timedelta(days=1))
    sales_now = profitability(txns, start, today).revenue
    before = profitability(txns, prev_start, prev_end).revenue
    covered = not txns.empty and txns["date"].min() <= pd.Timestamp(prev_start + timedelta(days=3))  # records cover last month's days
    if covered and before >= MIN_AMOUNT:
        change = (sales_now / before - 1) * 100
        if change >= GROWTH_PCT:
            out.append({"id": f"sales_up:{ym}", "kind": "good", "key": "sales_up",
                        "params": {"pct": round(change), "now": round(sales_now, 2), "before": round(before, 2)}})
        elif change <= -DROP_PCT:
            out.append({"id": f"sales_down:{ym}", "kind": "warn", "key": "sales_down",
                        "params": {"pct": round(-change), "now": round(sales_now, 2), "before": round(before, 2)}})
    return out
