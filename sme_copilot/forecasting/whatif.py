"""What-if simulation on top of the forecast model.

Scenarios mutate a copy of ``ForecastInputs``; both versions are projected and compared:
  delay_receivable  - a customer (or "biggest") pays N days later than expected
  loan              - disbursement now-ish, then EMIs (reducing balance) monthly
  revenue_change    - sales +/- pct (variable costs move with them)
  expense_change    - a category's cost changes by pct or a new monthly amount (e.g. hiring)
  one_off           - a single inflow/outflow on a date
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from sme_copilot.tools.analysis import add_months
from sme_copilot.tools.finance_math import emi_reducing
from sme_copilot.tools.trace import Trace, fmt

from .forecast import Flow, ForecastInputs, ForecastResult, Recurring, project


class Scenario(BaseModel):
    kind: Literal["delay_receivable", "loan", "revenue_change", "expense_change", "one_off"]
    customer: str | None = Field(None, description="customer name or 'biggest' (delay_receivable)")
    days: int | None = Field(None, ge=1, le=365, description="delay in days (delay_receivable)")
    amount: float | None = Field(None, gt=0, le=1e9, description="loan amount or one-off amount")
    annual_rate_pct: float = Field(12.0, ge=0, le=60, description="loan interest % p.a. (illustrative default)")
    months: int = Field(24, ge=1, le=120, description="loan tenure in months")
    start_in_days: int = Field(7, ge=0, le=90, description="days until disbursement / one-off")
    pct: float | None = Field(None, ge=-100, le=500, description="% change (revenue_change / expense_change)")
    category: str | None = Field(None, description="expense category (expense_change)")
    monthly_amount: float | None = Field(None, gt=0, le=1e8, description="new extra monthly cost (expense_change)")
    direction: Literal["in", "out"] = "out"
    description: str = Field("", max_length=120)

    @model_validator(mode="after")
    def _check(self):
        k = self.kind
        if k == "delay_receivable" and not self.days:
            raise ValueError("delay_receivable needs 'days'")
        if k in ("loan", "one_off") and not self.amount:
            raise ValueError(f"{k} needs 'amount'")
        if k == "revenue_change" and self.pct is None:
            raise ValueError("revenue_change needs 'pct'")
        if k == "expense_change" and (not self.category or (self.pct is None and self.monthly_amount is None)):
            raise ValueError("expense_change needs 'category' and 'pct' or 'monthly_amount'")
        return self


class ScenarioOutcome(BaseModel):
    description: str
    applied: bool
    detail: str


class WhatIfResult(BaseModel):
    horizon_days: int
    scenarios: list[ScenarioOutcome]
    baseline_end_balance: float
    scenario_end_balance: float
    end_balance_change: float
    baseline_min_balance: float
    scenario_min_balance: float
    scenario_min_balance_date: date
    baseline_first_negative_date: date | None
    scenario_first_negative_date: date | None
    loan_emi: float | None = None
    explanation: list[str]
    baseline_series: list[dict[str, Any]]
    scenario_series: list[dict[str, Any]]
    trace: Trace


def _biggest_customer(inp: ForecastInputs) -> str | None:
    totals: dict[str, float] = {}
    for f in inp.scheduled:
        if f.kind == "receivable":
            totals[f.category] = totals.get(f.category, 0) + f.amount
    return max(totals, key=totals.get) if totals else None


def apply(inp: ForecastInputs, sc: Scenario) -> tuple[ScenarioOutcome, float | None]:
    emi = None
    if sc.kind == "delay_receivable":
        name = sc.customer or "biggest"
        target = _biggest_customer(inp) if name.lower() in ("biggest", "largest", "top", "main") else None
        if target is None:
            low = name.lower()
            cands = {f.category for f in inp.scheduled if f.kind == "receivable"}
            target = next((c for c in cands if low in c.lower() or c.lower() in low), None)
        if target is None:
            return ScenarioOutcome(description=f"{name} pays {sc.days} days late", applied=False,
                                   detail="no open invoices found for that customer"), None
        moved = 0.0
        for f in inp.scheduled:
            if f.kind == "receivable" and f.category == target:
                f.day = f.day + timedelta(days=sc.days)
                moved += f.amount
        return ScenarioOutcome(description=f"{target} pays {sc.days} days late", applied=True,
                               detail=f"{fmt(moved)} of expected collections moved {sc.days} days later"), None
    if sc.kind == "loan":
        start = inp.as_of + timedelta(days=sc.start_in_days)
        emi = emi_reducing(sc.amount, sc.annual_rate_pct, sc.months)
        inp.scheduled.append(Flow(start, sc.amount, f"Loan disbursement {fmt(sc.amount)}", "loan"))
        d = add_months(start, 1)
        n = 0
        while d <= inp.as_of + timedelta(days=inp.horizon) and n < sc.months:
            inp.scheduled.append(Flow(d, -round(emi, 2), "Loan EMI", "emi", category="loan_repayment"))
            d = add_months(d, 1)
            n += 1
        return ScenarioOutcome(description=f"Take a {fmt(sc.amount)} loan at {sc.annual_rate_pct}% for {sc.months} "
                                           f"months", applied=True,
                               detail=f"EMI {fmt(round(emi, 2))}/month; {n} EMI(s) fall inside the horizon "
                                      f"(rate is an illustrative assumption)"), emi
    if sc.kind == "revenue_change":
        inp.revenue_scale *= 1 + sc.pct / 100
        for f in inp.scheduled:
            if f.kind == "receivable":
                f.amount = round(f.amount * (1 + sc.pct / 100), 2)
        return ScenarioOutcome(description=f"Sales {'+' if sc.pct >= 0 else ''}{sc.pct:g}%", applied=True,
                               detail="baseline sales, open-invoice collections and variable costs scaled"), None
    if sc.kind == "expense_change":
        cat = sc.category
        hits = [f for f in inp.scheduled if f.kind == "obligation" and f.category == cat]
        if sc.monthly_amount is not None:
            d = inp.as_of + timedelta(days=sc.start_in_days)
            first = d
            while d <= inp.as_of + timedelta(days=inp.horizon):
                inp.scheduled.append(Flow(d, -sc.monthly_amount, f"New {cat} cost", "obligation", category=cat))
                d = add_months(d, 1)
            inp.recurring.append(Recurring(f"New {cat}", cat, sc.monthly_amount, first.day, "what-if"))
            return ScenarioOutcome(description=f"Extra {cat} {fmt(sc.monthly_amount)}/month", applied=True,
                                   detail=f"added as a monthly payment starting {first.isoformat()}"), None
        if hits:
            for f in hits:
                f.amount = round(f.amount * (1 + sc.pct / 100), 2)
            return ScenarioOutcome(description=f"{cat} {'+' if sc.pct >= 0 else ''}{sc.pct:g}%", applied=True,
                                   detail=f"{len(hits)} scheduled {cat} payment(s) adjusted"), None
        if cat in ("inventory", "transport", "packaging", "marketing", "mobile_fees"):
            inp.variable_scale *= 1 + sc.pct / 100
            return ScenarioOutcome(description=f"{cat} {'+' if sc.pct >= 0 else ''}{sc.pct:g}%", applied=True,
                                   detail="variable-cost baseline scaled (approximation: all variable costs)"), None
        inp.fixed_extra_daily += inp.base_out_fixed_daily * sc.pct / 100
        return ScenarioOutcome(description=f"{cat} {'+' if sc.pct >= 0 else ''}{sc.pct:g}%", applied=True,
                               detail="fixed-cost baseline scaled (approximation)"), None
    # one_off
    d = inp.as_of + timedelta(days=sc.start_in_days)
    sign = 1 if sc.direction == "in" else -1
    inp.scheduled.append(Flow(d, sign * sc.amount, sc.description or "One-off", "one_off"))
    return ScenarioOutcome(description=f"One-off {'inflow' if sign > 0 else 'outflow'} {fmt(sc.amount)} on {d}",
                           applied=True, detail=sc.description or ""), None


def simulate(base_inputs: ForecastInputs, scenarios: list[Scenario]) -> WhatIfResult:
    base = project(base_inputs.clone())
    inp = base_inputs.clone()
    outcomes, emi = [], None
    for sc in scenarios:
        o, e = apply(inp, sc)
        outcomes.append(o)
        emi = e if e is not None else emi
    scen = project(inp)
    b_end, s_end = base.series[-1].balance, scen.series[-1].balance
    b_min = min(p.balance for p in base.series)
    s_min_p = min(scen.series, key=lambda p: p.balance)
    lines = [f"{o.description}: {o.detail}." if o.applied else f"Could not apply '{o.description}': {o.detail}."
             for o in outcomes]
    diff = s_end - b_end
    lines.append(f"In {base.horizon_days} days your balance would be {fmt(round(s_end))} instead of {fmt(round(b_end))} "
                 f"({'+' if diff >= 0 else '-'}{fmt(round(abs(diff)))}).")
    lines.append(f"Lowest point: {fmt(round(s_min_p.balance))} on {s_min_p.date.isoformat()} "
                 f"(baseline lowest {fmt(round(b_min))}).")
    if scen.first_negative_date and not base.first_negative_date:
        lines.append(f"Warning: this scenario takes you below zero on {scen.first_negative_date.isoformat()}.")
    elif base.first_negative_date and not scen.first_negative_date:
        lines.append("This scenario avoids the cash shortfall in the baseline forecast.")
    t = Trace(formula="scenario forecast - baseline forecast (same model, adjusted inputs)",
              period=f"{base_inputs.as_of} + {base.horizon_days} days")
    t.step("Baseline end balance", b_end)
    t.step("Scenario end balance", s_end)
    t.step("Change", round(diff, 2), f"{fmt(s_end)} - {fmt(b_end)}")
    t.step("Scenario minimum balance", s_min_p.balance)
    if emi:
        t.step("Loan EMI", round(emi, 2), "P*r*(1+r)^n/((1+r)^n-1)")
    t.rows(base_inputs.trace_rows)
    t.assumptions += base.trace.assumptions
    weekly = lambda res: [{"date": p.date.isoformat(), "balance": p.balance} for p in res.series[::7]] + \
        [{"date": res.series[-1].date.isoformat(), "balance": res.series[-1].balance}]  # noqa: E731
    return WhatIfResult(
        horizon_days=base.horizon_days, scenarios=outcomes, baseline_end_balance=b_end, scenario_end_balance=s_end,
        end_balance_change=round(diff, 2), baseline_min_balance=round(b_min, 2),
        scenario_min_balance=s_min_p.balance, scenario_min_balance_date=s_min_p.date,
        baseline_first_negative_date=base.first_negative_date, scenario_first_negative_date=scen.first_negative_date,
        loan_emi=round(emi, 2) if emi else None, explanation=lines, baseline_series=weekly(base),
        scenario_series=weekly(scen), trace=t)


__all__ = ["Scenario", "WhatIfResult", "simulate", "ForecastResult"]
