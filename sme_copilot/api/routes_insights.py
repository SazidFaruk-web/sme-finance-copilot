"""Dashboard, forecast, what-if, alerts and digest endpoints (read-mostly, Tier 0)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sme_copilot.agent.executor import execute
from sme_copilot.config import get_settings
from sme_copilot.db import get_db
from sme_copilot.forecasting.alerts import alert_dict, refresh_alerts
from sme_copilot.forecasting.digest import build_digest
from sme_copilot.forecasting.forecast import build_inputs, project
from sme_copilot.forecasting.whatif import Scenario, simulate
from sme_copilot.models import Business, User
from sme_copilot.security import audit
from sme_copilot.tools import repo
from sme_copilot.tools.analysis import (
    income_expense_summary,
    monthly_table,
    profitability,
    resolve_period,
    top_cost_drivers,
    aging,
)

from .deps import as_of_today, current_user, require_tier, tool_context
from .schemas import SettingsIn

router = APIRouter(prefix="/api")


def _biz(db: Session, user: User) -> Business:
    b = db.get(Business, user.business_id)
    if b is None:
        raise HTTPException(404, "business not found")
    return b


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    b = _biz(db, user)
    as_of = as_of_today()
    txns = repo.load_transactions(db, b.id, end=as_of)
    inv = repo.load_invoices(db, b.id)
    obl = repo.load_obligations(db, b.id)
    fc = project(build_inputs(txns, inv, obl, b, as_of, 90))
    s, e, l_this = resolve_period("this_month", as_of)
    this_m = income_expense_summary(txns, s, e, l_this)
    prof_m = profitability(txns, s, e, l_this)
    costs_m = top_cost_drivers(txns, s, e, l_this, top_n=8)
    s, e, l_last = resolve_period("last_month", as_of)
    last_m = income_expense_summary(txns, s, e, l_last)
    s, e, l3 = resolve_period("last_3_months", as_of)
    prof = profitability(txns, s, e, l3)
    costs = top_cost_drivers(txns, s, e, l3, top_n=8)
    s12, e12, _ = resolve_period("last_12_months", as_of)
    monthly = monthly_table(txns[(txns["date"] >= str(s12))]) if not txns.empty else []
    ar = aging(inv, as_of, "receivable", txns) if not inv.empty else None
    alerts = refresh_alerts(db, b, as_of, fc=fc)
    db.commit()
    s30 = next(x for x in fc.summaries if x.days == 30)
    return {
        "business": {"name": b.name, "sector": b.sector, "district": b.district,
                     "number_style": (b.prefs or {}).get("number_style", "lakh"),
                     "language": (b.prefs or {}).get("language", "en")},
        "as_of": as_of.isoformat(),
        "record_count": len(txns),
        "kpis": {
            "cash_balance": fc.start_balance, "income_this_month": this_m.total_income,
            "expense_this_month": this_m.total_expense, "net_last_month": last_m.net_cash_flow,
            "gross_margin_3m": prof.gross_margin_pct, "net_margin_3m": prof.net_margin_pct,
            "receivables_outstanding": ar.total_outstanding if ar else 0, "receivables_overdue": ar.overdue_total if ar else 0,
            "forecast_min_30d": s30.min_balance, "runway_months": fc.runway_months,
            "profit_this_month": prof_m.operating_profit,
        },
        "kpi_traces": {"cash_balance": fc.trace.model_dump(mode="json"), "margins": prof.trace.model_dump(mode="json"),
                       "income_this_month": this_m.trace.model_dump(mode="json"),
                       "profit_this_month": prof_m.trace.model_dump(mode="json"),
                       "receivables": ar.trace.model_dump(mode="json") if ar else None},
        "forecast": {"series": [{"date": p.date.isoformat(), "balance": p.balance, "low": p.low, "high": p.high,
                                 "events": p.events} for p in fc.series],
                     "summaries": [x.model_dump(mode="json") for x in fc.summaries],
                     "first_negative_date": fc.first_negative_date.isoformat() if fc.first_negative_date else None,
                     "threshold": fc.low_balance_threshold, "notes": fc.notes,
                     "scheduled_items": fc.scheduled_items[:20], "recurring": fc.recurring},
        "monthly": [m.model_dump() for m in monthly],
        "expense_breakdown": [d.model_dump() for d in costs.drivers],
        "expense_this_month": [d.model_dump() for d in costs_m.drivers],
        "receivables_aging": _aging_buckets(ar),
        "alerts": [alert_dict(a) for a in alerts[:12]],
        "guidance_alerts": [alert_dict(a) for a in alerts],
        # Keep personal reminders visible even when many higher-priority system alerts exist.
        "reminders": [alert_dict(a) for a in alerts if a.kind == "custom"],
    }


def _aging_buckets(ar: Any) -> dict[str, float]:
    """Receivables owed by days past due: not yet due / 0-30 / 31-60 / 61+."""
    out = {"not_due": 0.0, "0-30": 0.0, "31-60": 0.0, "61+": 0.0}
    for it in (ar.items if ar else []):
        d = it.days_past_due
        out["not_due" if d <= 0 else "0-30" if d <= 30 else "31-60" if d <= 60 else "61+"] += it.outstanding
    return {k: round(v, 2) for k, v in out.items()}


@router.get("/forecast")
def get_forecast(horizon: Literal[30, 60, 90] = 90, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    b = _biz(db, user)
    as_of = as_of_today()
    fc = project(build_inputs(repo.load_transactions(db, b.id, end=as_of), repo.load_invoices(db, b.id),
                              repo.load_obligations(db, b.id), b, as_of, horizon))
    return fc.model_dump(mode="json")


class WhatIfIn(BaseModel):
    scenarios: list[Scenario] = Field(..., min_length=1, max_length=4)
    horizon_days: Literal[30, 60, 90] = 90


@router.post("/whatif")
def whatif(body: WhatIfIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    out = execute(tool_context(db, user), "run_what_if", body.model_dump(mode="json"))
    if out.status != "ok":
        raise HTTPException(422, out.message)
    return out.data


@router.get("/alerts")
def alerts(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = refresh_alerts(db, _biz(db, user), as_of_today())
    db.commit()
    return [alert_dict(a) for a in rows]


@router.post("/alerts/{alert_id}/{action}")
def alert_action(alert_id: int, action: Literal["acknowledged", "dismissed"], user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    out = execute(tool_context(db, user), "acknowledge_alert", {"alert_id": alert_id, "action": action})
    if out.status != "ok":
        raise HTTPException(403 if out.status in ("denied", "blocked") else 404, out.message)
    return out.data


@router.get("/digest")
def digest(period: Literal["daily", "weekly"] = "weekly", user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> dict[str, Any]:
    d = build_digest(db, _biz(db, user), as_of_today(), period)
    db.commit()
    return d.model_dump(mode="json")


@router.get("/settings")
def get_settings_(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    b = _biz(db, user)
    return {"number_style": (b.prefs or {}).get("number_style", "lakh"),
            "language": (b.prefs or {}).get("language", "en"),
            "low_balance_threshold": float(b.low_balance_threshold or 0),
            "step_up_amount": get_settings().step_up_amount}


@router.patch("/settings")
def patch_settings(body: SettingsIn, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)) -> dict[str, Any]:
    b = _biz(db, user)
    prefs = dict(b.prefs or {})
    if body.number_style:
        prefs["number_style"] = body.number_style
    if body.language:
        prefs["language"] = body.language
    b.prefs = prefs
    if body.low_balance_threshold is not None:
        b.low_balance_threshold = body.low_balance_threshold
    db.commit()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=b.id, event_type="operation",
                 action="update_settings", tier=1, inputs=body.model_dump(exclude_none=True))
    return get_settings_(user, db)
