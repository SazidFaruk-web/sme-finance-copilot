"""Daily / weekly digest: what needs attention, with one-click suggested actions."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from sme_copilot.models import Business
from sme_copilot.tools import repo
from sme_copilot.tools.analysis import aging, income_expense_summary, resolve_period
from sme_copilot.tools.money import format_bdt
from sme_copilot.tools.trace import Trace

from .alerts import alert_dict, refresh_alerts
from .forecast import forecast


class SuggestedAction(BaseModel):
    title: str
    tool: str
    args: dict[str, Any]
    reason: str


class DigestResult(BaseModel):
    period: str
    as_of: date
    headline: str
    kpis: dict[str, float | None]
    alerts: list[dict[str, Any]]
    actions: list[SuggestedAction]
    upcoming: list[dict[str, Any]]
    trace: Trace


def build_digest(session: Session, business: Business, as_of: date,
                 period: Literal["daily", "weekly"] = "weekly") -> DigestResult:
    style = (business.prefs or {}).get("number_style", "lakh")
    txns = repo.load_transactions(session, business.id, end=as_of)
    inv = repo.load_invoices(session, business.id)
    obl = repo.load_obligations(session, business.id)
    fc = forecast(txns, inv, obl, business, as_of, 90)
    alerts = refresh_alerts(session, business, as_of, fc=fc)

    s, e, _ = resolve_period("this_month", as_of)
    this_m = income_expense_summary(txns, s, e)
    s2, e2, _ = resolve_period("last_month", as_of)
    last_m = income_expense_summary(txns, s2, e2)
    ar = aging(inv, as_of, "receivable") if not inv.empty else None
    s30 = next(x for x in fc.summaries if x.days == 30)
    window = 1 if period == "daily" else 7
    upcoming = [i for i in fc.scheduled_items if date.fromisoformat(i["date"]) <= as_of + timedelta(days=window * 2)]

    kpis = {"cash_balance": fc.start_balance, "income_this_month": this_m.total_income,
            "expense_this_month": this_m.total_expense, "net_last_month": last_m.net_cash_flow,
            "forecast_min_30d": s30.min_balance, "forecast_end_30d": s30.end_balance,
            "receivables_overdue": ar.overdue_total if ar else 0.0, "open_alerts": float(len(alerts)),
            "runway_months": fc.runway_months}

    actions: list[SuggestedAction] = []
    seen_tools: set[str] = set()
    for a in alerts:
        st = (a.data or {}).get("suggested_tool")
        if st and len(actions) < 4:
            actions.append(SuggestedAction(title=f"{'Send reminder' if st['name'] == 'create_payment_reminder' else 'Review'}: "
                                                 f"{a.title}", tool=st["name"], args=st["args"], reason=a.message[:160]))
            seen_tools.add(st["name"])
    if s30.min_balance < fc.low_balance_threshold:
        actions.append(SuggestedAction(title="Explore financing options for the gap", tool="match_financing",
                                       args={"amount": round(max(50_000, fc.low_balance_threshold - s30.min_balance), -3)},
                                       reason="Forecast dips below your safety level within 30 days."))
    if any(a.kind == "overdue_invoice" for a in alerts) and "draft_invoice_followup" not in seen_tools:
        top = next(a for a in alerts if a.kind == "overdue_invoice")
        actions.append(SuggestedAction(title=f"Draft a follow-up message to {top.data.get('counterparty')}",
                                       tool="draft_invoice_followup", args={"invoice_id": top.data.get("invoice_id")},
                                       reason="Polite written follow-ups speed up collection."))

    crit = sum(1 for a in alerts if a.severity == "critical")
    warn = sum(1 for a in alerts if a.severity == "warning")
    headline = (f"{crit} critical and {warn} warning item(s). Cash now {format_bdt(fc.start_balance, style=style)}; "
                f"lowest in the next 30 days {format_bdt(s30.min_balance, style=style)} on {s30.min_balance_date}.")
    t = Trace(formula="digest = open alerts + KPIs from summary, aging and forecast tools", period=f"as of {as_of}")
    for k, v in kpis.items():
        t.step(k.replace("_", " "), v)
    return DigestResult(period=period, as_of=as_of, headline=headline, kpis=kpis,
                        alerts=[alert_dict(a) for a in alerts[:8]], actions=actions[:5], upcoming=upcoming[:10], trace=t)
