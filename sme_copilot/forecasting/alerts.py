"""Proactive alerts and the daily/weekly digest.

Alert sources (all deterministic):
  low_balance        forecast minimum below threshold / below zero within 30 days
  overdue_invoice    receivable past due (critical after 60 days)
  payable_due        supplier bill due within 7 days or overdue
  obligation_due     rent / salary / EMI / VAT within 7 days (explicit or detected recurring)
  compliance_due     configured compliance date within 10 days (marked "verify")
  unusual_spending   anomaly-flagged outflow in the last 30 days
  spending_spike     this month's category spend > 1.5x its 3-month average
  duplicates         possible duplicate rows awaiting review
  seasonal_prep      festival within 45 days that lifted sales last year

Alerts are upserted by ``dedupe_key`` so re-running never spams, and a dismissed alert stays dismissed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.config import load_yaml
from sme_copilot.models import Alert, Business
from sme_copilot.tools import repo
from sme_copilot.tools.analysis import add_months, aging, seasonality
from sme_copilot.tools.money import format_bdt

from .forecast import ForecastResult, forecast

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class AlertCandidate:
    kind: str
    severity: str
    title: str
    message: str
    dedupe_key: str
    due_date: date | None = None
    data: dict[str, Any] = field(default_factory=dict)


@lru_cache
def compliance_rules() -> dict[str, Any]:
    return load_yaml("compliance_bd.yaml")


def _applies(rule: dict[str, Any], business: Business) -> bool:
    for k, v in (rule.get("applies_if") or {}).items():
        if bool(getattr(business, k, False)) != bool(v):
            return False
    return True


def compliance_due_dates(business: Business, as_of: date, window: int = 10) -> list[tuple[dict[str, Any], date]]:
    out = []
    for r in compliance_rules().get("rules", []):
        rec = r.get("recurrence")
        if not rec or not _applies(r, business):
            continue
        cands: list[date] = []
        if "monthly" in rec:
            day = int(rec["monthly"]["day"])
            for m in (0, 1):
                d = add_months(as_of.replace(day=1), m)
                cands.append(d.replace(day=min(day, 28)))
        if "yearly" in rec:
            y = rec["yearly"]
            for yr in (as_of.year, as_of.year + 1):
                cands.append(date(yr, int(y["month"]), int(y["day"])))
        for d in cands:
            if as_of <= d <= as_of + timedelta(days=window):
                out.append((r, d))
    return out


def _m(v: float, style: str) -> str:
    return format_bdt(v, style=style)


def compute_alerts(business: Business, txns: pd.DataFrame, invoices: pd.DataFrame, obligations: list[Any],
                   as_of: date, fc: ForecastResult | None = None) -> list[AlertCandidate]:
    style = (business.prefs or {}).get("number_style", "lakh")
    out: list[AlertCandidate] = []
    fc = fc or forecast(txns, invoices, obligations, business, as_of, 90)

    # Low balance (30-day window)
    s30 = next((s for s in fc.summaries if s.days == 30), None)
    if s30:
        if s30.min_balance < 0:
            out.append(AlertCandidate(
                "low_balance", "critical", "Cash shortfall expected within 30 days",
                f"Forecast balance drops to {_m(s30.min_balance, style)} on {s30.min_balance_date}. Consider "
                f"chasing overdue invoices, delaying non-essential purchases, or short-term financing.",
                f"low_balance:neg:{s30.min_balance_date.isoformat()[:7]}", s30.min_balance_date,
                {"min_balance": s30.min_balance, "date": s30.min_balance_date.isoformat()}))
        elif s30.min_balance < fc.low_balance_threshold:
            out.append(AlertCandidate(
                "low_balance", "warning", "Low balance risk",
                f"Forecast balance dips to {_m(s30.min_balance, style)} on {s30.min_balance_date}, below your "
                f"safety level of {_m(fc.low_balance_threshold, style)}.",
                f"low_balance:low:{s30.min_balance_date.isoformat()[:7]}", s30.min_balance_date,
                {"min_balance": s30.min_balance}))

    # Receivables / payables
    if not invoices.empty:
        ar = aging(invoices, as_of, "receivable")
        for it in ar.items:
            if it.days_past_due > 0:
                sev = "critical" if it.days_past_due > 60 else "warning"
                out.append(AlertCandidate(
                    "overdue_invoice", sev, f"Overdue: {it.counterparty} owes {_m(it.outstanding, style)}",
                    f"Invoice {it.invoice_no or it.invoice_id} was due {it.due_date} ({it.days_past_due} days ago). "
                    f"Send a reminder or a follow-up message.", f"overdue:{it.invoice_id}", it.due_date,
                    {"invoice_id": it.invoice_id, "counterparty": it.counterparty, "outstanding": it.outstanding,
                     "days_past_due": it.days_past_due,
                     "suggested_tool": {"name": "create_payment_reminder", "args": {"invoice_id": it.invoice_id}}}))
        ap = aging(invoices, as_of, "payable")
        for it in ap.items:
            if it.days_past_due > -7:
                sev = "warning" if it.days_past_due > 0 else "info"
                when = "overdue" if it.days_past_due > 0 else f"due {it.due_date}"
                out.append(AlertCandidate(
                    "payable_due", sev, f"Supplier bill {when}: {it.counterparty} {_m(it.outstanding, style)}",
                    f"Bill {it.invoice_no or it.invoice_id} to {it.counterparty} is {when}.",
                    f"payable:{it.invoice_id}", it.due_date,
                    {"invoice_id": it.invoice_id, "outstanding": it.outstanding,
                     "suggested_tool": {"name": "pay_supplier_invoice", "args": {"invoice_id": it.invoice_id}}}))

    # Upcoming obligations within 7 days
    for item in fc.scheduled_items:
        d = date.fromisoformat(item["date"])
        if item["kind"] == "obligation" and d <= as_of + timedelta(days=7):
            out.append(AlertCandidate(
                "obligation_due", "info", f"{item['label']} due {d.strftime('%d %b')}",
                f"{item['label']} of about {_m(abs(item['amount']), style)} is due on {d}. "
                f"Expected balance that day: see forecast.", f"obligation:{item['label']}:{d.isoformat()}", d,
                {"amount": abs(item["amount"])}))

    # Compliance reminders (flagged for verification)
    for rule, d in compliance_due_dates(business, as_of):
        out.append(AlertCandidate(
            "compliance_due", "info", f"{rule['title']} - around {d.strftime('%d %b')} (verify)",
            rule["summary"].strip() + " [Configured reminder - verify the date with the authority.]",
            f"compliance:{rule['id']}:{d.isoformat()}", d, {"rule_id": rule["id"], "source_url": rule.get("source_url"),
                                                              "verified": rule.get("verified", False)}))

    if not txns.empty:
        recent = txns[txns["date"] >= pd.Timestamp(as_of - timedelta(days=30))]
        # Unusual spending
        for r in recent[recent["is_anomaly"] & (recent["direction"] == "out")].itertuples():
            out.append(AlertCandidate(
                "unusual_spending", "warning", f"Unusual payment: {_m(r.amount, style)} ({r.category})",
                f"{r.date.date()}: {r.counterparty or r.description[:60]} - looks unusual. Check it is correct.",
                f"anomaly:{r.id}", r.date.date(), {"transaction_id": int(r.id)}))
        # Category spikes this month vs 3-month average
        m0 = pd.Timestamp(as_of.replace(day=1))
        p3 = pd.Timestamp(add_months(as_of.replace(day=1), -3))
        this = txns[(txns["date"] >= m0) & (txns["direction"] == "out")].groupby("category")["amount"].sum()
        prev = txns[(txns["date"] >= p3) & (txns["date"] < m0) & (txns["direction"] == "out")] \
            .groupby("category")["amount"].sum() / 3
        for cat, amt in this.items():
            avg = float(prev.get(cat, 0))
            if avg > 0 and amt > 1.5 * avg and amt - avg > 10_000 and cat not in ("loan_repayment", "equipment"):
                out.append(AlertCandidate(
                    "spending_spike", "warning", f"{cat.replace('_', ' ').title()} spending is up",
                    f"This month {_m(float(amt), style)} vs a 3-month average of {_m(avg, style)} "
                    f"({round((float(amt) / avg - 1) * 100)}% higher).", f"spike:{cat}:{as_of.strftime('%Y-%m')}",
                    None, {"category": cat, "this_month": float(amt), "avg": avg}))

    # Seasonal preparation
    seas = seasonality(txns, as_of) if not txns.empty else None
    if seas:
        for u in seas.upcoming_events:
            if u["days_away"] <= 45 and (u["last_year_uplift_pct"] or 0) >= 20:
                out.append(AlertCandidate(
                    "seasonal_prep", "info", f"{u['event']} in ~{u['days_away']} days",
                    f"Last time your sales rose about {u['last_year_uplift_pct']}% around {u['event']}. Plan stock "
                    f"and working capital now.", f"season:{u['event']}:{u['date']}",
                    date.fromisoformat(u["date"]), u))
    return out


def refresh_alerts(session: Session, business: Business, as_of: date, *, fc: ForecastResult | None = None) -> list[Alert]:
    """Recompute alerts and upsert by dedupe key. Returns open + scheduled alerts, most severe first."""
    txns = repo.load_transactions(session, business.id, end=as_of)
    inv = repo.load_invoices(session, business.id)
    obl = repo.load_obligations(session, business.id)
    cands = compute_alerts(business, txns, inv, obl, as_of, fc)
    existing = {a.dedupe_key: a for a in session.scalars(select(Alert).where(Alert.business_id == business.id))}
    live_keys = set()
    for c in cands:
        live_keys.add(c.dedupe_key)
        a = existing.get(c.dedupe_key)
        if a is None:
            session.add(Alert(business_id=business.id, kind=c.kind, severity=c.severity, title=c.title[:200],
                              message=c.message, due_date=c.due_date, dedupe_key=c.dedupe_key[:200], data=c.data))
        elif a.status == "open":
            a.severity, a.title, a.message, a.data = c.severity, c.title[:200], c.message, c.data
    # Auto-resolve system alerts whose condition no longer holds (e.g. invoice got paid).
    for key, a in existing.items():
        if a.created_by == "system" and a.status == "open" and key not in live_keys:
            a.status = "resolved"
    session.flush()
    rows = session.scalars(select(Alert).where(Alert.business_id == business.id,
                                               Alert.status.in_(["open", "scheduled"]))).all()
    return sorted(rows, key=lambda a: (SEVERITY_ORDER.get(a.severity, 9), a.due_date or date.max))


def alert_dict(a: Alert) -> dict[str, Any]:
    return {"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "message": a.message,
            "due_date": a.due_date.isoformat() if a.due_date else None, "status": a.status,
            "created_by": a.created_by, "data": a.data or {}}
