"""Forecast, what-if, alerts and digest tools."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from sme_copilot.forecasting.alerts import alert_dict, refresh_alerts
from sme_copilot.forecasting.digest import DigestResult, build_digest
from sme_copilot.forecasting.forecast import ForecastResult, build_inputs, project
from sme_copilot.forecasting.whatif import Scenario, WhatIfResult, simulate
from sme_copilot.models import Alert
from sme_copilot.tools import repo

from .toolkit import ToolContext, tool


class ForecastArgs(BaseModel):
    horizon_days: Literal[30, 60, 90] = 90


def _inputs(ctx: ToolContext, horizon: int):
    return build_inputs(ctx.txns(), ctx.invoices(), repo.load_obligations(ctx.session, ctx.business.id), ctx.business,
                        ctx.as_of, horizon)


@tool("forecast_cash_flow", "Forecast cash balance for the next 30/60/90 days: daily series with an 80% band, "
      "lowest point, first date below zero or below the safety level, runway, scheduled collections and payments.",
      ForecastArgs, 0, category="forecast", result_model=ForecastResult, advisory=True)
def forecast_cash_flow(ctx: ToolContext, a: ForecastArgs):
    res = project(_inputs(ctx, a.horizon_days))
    # Keep the model's view compact: weekly points are enough to talk about; the UI gets all days via /api.
    res.series = res.series[::7] + ([res.series[-1]] if res.series else [])
    return res


class WhatIfArgs(BaseModel):
    scenarios: list[Scenario] = Field(..., min_length=1, max_length=4)
    horizon_days: Literal[30, 60, 90] = 90


@tool("run_what_if", "Simulate scenarios against the cash-flow forecast, e.g. a customer paying N days late "
      "(kind=delay_receivable, customer='biggest'), taking a loan (kind=loan, amount, annual_rate_pct, months), "
      "sales up/down (kind=revenue_change, pct), cost changes (kind=expense_change, category, pct or "
      "monthly_amount), one-off payments (kind=one_off).", WhatIfArgs, 0, category="forecast",
      result_model=WhatIfResult, advisory=True)
def run_what_if(ctx: ToolContext, a: WhatIfArgs):
    return simulate(_inputs(ctx, a.horizon_days), a.scenarios, style=ctx.style)


class AlertsArgs(BaseModel):
    severity: Literal["", "critical", "warning", "info"] = ""


class AlertsResult(BaseModel):
    count: int
    alerts: list[dict]


@tool("list_alerts", "Current alerts: low balance risk, overdue invoices, upcoming rent/salary/EMI/VAT, unusual "
      "spending, spending spikes, seasonal preparation.", AlertsArgs, 0, category="forecast", result_model=AlertsResult)
def list_alerts(ctx: ToolContext, a: AlertsArgs):
    rows = refresh_alerts(ctx.session, ctx.business, ctx.as_of)
    if a.severity:
        rows = [r for r in rows if r.severity == a.severity]
    return AlertsResult(count=len(rows), alerts=[alert_dict(r) for r in rows[:15]])


class DigestArgs(BaseModel):
    period: Literal["daily", "weekly"] = "weekly"


@tool("get_digest", "What needs my attention: headline, KPIs, top alerts and suggested next actions.",
      DigestArgs, 0, category="forecast", result_model=DigestResult)
def get_digest(ctx: ToolContext, a: DigestArgs):
    return build_digest(ctx.session, ctx.business, ctx.as_of, a.period)


class AckArgs(BaseModel):
    alert_id: int
    action: Literal["acknowledged", "dismissed"] = "acknowledged"


class AckResult(BaseModel):
    alert_id: int
    status: str


@tool("acknowledge_alert", "Mark an alert as acknowledged or dismissed.", AckArgs, 1, category="action",
      result_model=AckResult)
def acknowledge_alert(ctx: ToolContext, a: AckArgs):
    al = ctx.session.get(Alert, a.alert_id)
    if al is None or al.business_id != ctx.business.id:
        raise LookupError("alert not found")
    al.status = a.action
    return AckResult(alert_id=al.id, status=al.status)


class ScheduleArgs(BaseModel):
    title: str = Field(..., min_length=3, max_length=160, description="What to be reminded about")
    due_date: date | None = Field(None, description="When (YYYY-MM-DD). Defaults to 7 days from today.")
    notes: str = Field("", max_length=500)


class ScheduleResult(BaseModel):
    alert_id: int
    title: str
    due_date: date
    status: str


@tool("schedule_alert", "Schedule a custom alert/reminder for the owner (e.g. 'pay VAT on the 15th', 'reorder "
      "zippers before Eid').", ScheduleArgs, 1, category="action", result_model=ScheduleResult)
def schedule_alert(ctx: ToolContext, a: ScheduleArgs):
    from datetime import timedelta
    due = a.due_date or ctx.as_of + timedelta(days=7)
    if due < ctx.as_of:
        raise ValueError("due date is in the past")
    al = Alert(business_id=ctx.business.id, kind="custom", severity="info", title=a.title, message=a.notes,
               due_date=due, status="scheduled", created_by="agent" if ctx.origin == "agent" else "user",
               dedupe_key=f"custom:{ctx.request_id}:{a.title[:60]}:{due.isoformat()}")
    ctx.session.add(al)
    ctx.session.flush()
    return ScheduleResult(alert_id=al.id, title=al.title, due_date=due, status=al.status)
