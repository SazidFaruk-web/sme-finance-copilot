"""Deterministic 30/60/90-day cash-flow forecast.

Model (transparent by design, so every number can be explained to a shop owner):

  balance[t] = balance[t-1] + baseline_in[t] - baseline_out[t] + scheduled[t]

* Starting balance: opening balance + recorded inflows - outflows (tools/repo.cash_position).
* Scheduled flows (exact dates):
    - open receivables, expected on due date + that customer's historical average delay;
      invoices > 90 days overdue are counted at 50 % (collection risk);
    - open payables on their due date (overdue -> in 3 days);
    - recurring obligations: explicit ones (rent, salary, EMI, VAT...) plus ones detected from
      history (same category, roughly monthly, similar amount).
* Baseline (everything else), from the last 90 days of history:
    - inflow = sales not explained by invoice collections, + other income;
    - collections from *new* credit sales (invoices not issued yet) at the historical rate, but
      only after the typical issue-to-payment lag (before that, open invoices cover it);
    - outflow split into variable (scales with sales in what-ifs) and fixed/other;
    - categories covered by recurring obligations are removed to avoid double counting;
    - multiplied by a month-of-year seasonal factor when last year's same month is known.
* Uncertainty: 80 % band = ±1.28 * σ(weekly net) * √(t/7). Weekly (not daily) volatility is used
  because lumpy purchases and collections partly offset within a week.
"""
from __future__ import annotations

import copy
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Any

import pandas as pd
from pydantic import BaseModel

from sme_copilot.tools.analysis import add_months, payment_behavior
from sme_copilot.tools.categorize import behavior
from sme_copilot.tools.repo import cash_position
from sme_copilot.tools.trace import Trace, fmt

RECURRING_CATEGORIES = ("rent", "salary", "loan_repayment", "utilities", "tax_vat")
LOOKBACK_DAYS = 90
Z80 = 1.2816


@dataclass
class Flow:
    day: date
    amount: float  # signed: + inflow, - outflow
    label: str
    kind: str  # receivable | payable | obligation | loan | one_off | emi
    ref: str = ""
    probability: float = 1.0
    category: str = ""


@dataclass
class Recurring:
    name: str
    category: str
    amount: float
    day_of_month: int
    source: str  # explicit | detected
    frequency: str = "monthly"
    next_due: date | None = None


@dataclass
class ForecastInputs:
    as_of: date
    horizon: int
    start_balance: float
    base_in_daily: float
    base_out_variable_daily: float
    base_out_fixed_daily: float
    month_factor: dict[int, float]
    scheduled: list[Flow]
    recurring: list[Recurring]
    weekly_std: float
    low_threshold: float
    notes: list[str] = field(default_factory=list)
    trace_rows: list[int] = field(default_factory=list)
    base_collections_daily: float = 0.0  # future credit-sale collections (after the lag)
    collection_lag_days: int = 30
    revenue_scale: float = 1.0  # what-if knob
    variable_scale: float = 1.0
    fixed_extra_daily: float = 0.0

    def clone(self) -> "ForecastInputs":
        return copy.deepcopy(self)


class DayPoint(BaseModel):
    date: date
    inflow: float
    outflow: float
    net: float
    balance: float
    low: float
    high: float
    events: list[str]


class HorizonSummary(BaseModel):
    days: int
    end_balance: float
    total_inflow: float
    total_outflow: float
    min_balance: float
    min_balance_date: date


class ForecastResult(BaseModel):
    as_of: date
    horizon_days: int
    start_balance: float
    summaries: list[HorizonSummary]
    first_negative_date: date | None
    first_below_threshold_date: date | None
    low_balance_threshold: float
    runway_months: float | None
    avg_monthly_net: float
    scheduled_items: list[dict[str, Any]]
    recurring: list[dict[str, Any]]
    series: list[DayPoint]
    notes: list[str]
    confidence_band_pct: int = 80
    trace: Trace


# ----------------------------------------------------------------------------- recurring detection
def detect_recurring(txns: pd.DataFrame, as_of: date) -> list[Recurring]:
    """Find monthly obligations in history: >= 3 of the last 4 months have a payment in the
    category, and amounts are stable (each within 35 % of the median)."""
    out: list[Recurring] = []
    if txns.empty:
        return out
    start = pd.Timestamp(add_months(as_of.replace(day=1), -4))
    df = txns[(txns["date"] >= start) & (txns["date"] <= pd.Timestamp(as_of)) & (txns["direction"] == "out")]
    for cat in RECURRING_CATEGORIES:
        c = df[df["category"] == cat]
        if c.empty:
            continue
        c = c.copy()
        c["ym"] = c["date"].dt.strftime("%Y-%m")
        monthly = c.groupby("ym").agg(amount=("amount", "sum"), day=("date", lambda s: int(s.dt.day.median())))
        if len(monthly) < 3:
            continue
        med = float(median(monthly["amount"]))
        if med <= 0 or any(abs(a - med) > 0.35 * med for a in monthly["amount"].tolist()[-3:]):
            continue
        dom = int(median(monthly["day"]))
        out.append(Recurring(name=cat.replace("_", " ").title(), category=cat, amount=round(med, 2),
                             day_of_month=min(dom, 28), source="detected"))
    return out


def _next_dates(rec: Recurring, as_of: date, horizon: int) -> list[date]:
    end = as_of + timedelta(days=horizon)
    step = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(rec.frequency, 1)
    if rec.frequency == "once":
        return [rec.next_due] if rec.next_due and as_of < rec.next_due <= end else []
    if rec.next_due:
        d = rec.next_due
        while d <= as_of:
            d = add_months(d, step)
    else:
        d = as_of.replace(day=min(rec.day_of_month, 28))
        if d <= as_of:
            d = add_months(d, 1)
    days = []
    while d <= end:
        days.append(d)
        d = add_months(d, step)
    return days


# ----------------------------------------------------------------------------- inputs
def build_inputs(txns: pd.DataFrame, invoices: pd.DataFrame, obligations: list[Any], business: Any,
                 as_of: date, horizon: int = 90) -> ForecastInputs:
    start_balance, _ = cash_position(business, txns, as_of)
    notes: list[str] = []

    # Recurring obligations: explicit first, detected for categories not covered.
    recurring: list[Recurring] = []
    for o in obligations:
        recurring.append(Recurring(name=o.name, category=o.category, amount=float(o.amount),
                                   day_of_month=int(o.day_of_month or 1), source="explicit",
                                   frequency=o.frequency, next_due=o.next_due))
    covered = {r.category for r in recurring}
    for r in detect_recurring(txns, as_of):
        if r.category not in covered:
            recurring.append(r)
            covered.add(r.category)
    if any(r.source == "detected" for r in recurring):
        notes.append("Recurring payments detected from your history: " +
                     ", ".join(f"{r.name} ~{fmt(r.amount)} around day {r.day_of_month}" for r in recurring
                               if r.source == "detected") + ".")

    # Baseline from the lookback window.
    lb_start = as_of - timedelta(days=LOOKBACK_DAYS - 1)
    hist = txns[(txns["date"] >= pd.Timestamp(lb_start)) & (txns["date"] <= pd.Timestamp(as_of))] \
        if not txns.empty else txns
    days_of_data = LOOKBACK_DAYS
    if not txns.empty:
        first = txns["date"].min().date()
        days_of_data = max(14, min(LOOKBACK_DAYS, (as_of - first).days + 1))
    if days_of_data < LOOKBACK_DAYS:
        notes.append(f"Only {days_of_data} days of history; the forecast is less certain.")

    beh_in = defaultdict(float)
    beh_out = defaultdict(float)
    for r in hist.itertuples() if not hist.empty else []:
        b = behavior(r.category) if r.category != "uncategorized" else ("variable" if r.direction == "out" else "revenue")
        if r.direction == "in":
            if b in ("revenue", "other_income"):
                beh_in[b] += r.amount
        else:
            if r.category in covered:
                continue  # modelled as a scheduled obligation
            if b in ("financing", "capex"):
                continue  # lumpy / modelled explicitly
            key = "variable" if b in ("variable", "cogs") else "fixed"
            beh_out[key] += r.amount

    # Remove invoice collections from baseline sales (they are scheduled explicitly).
    collected = 0.0
    if not invoices.empty:
        paid = invoices[(invoices["kind"] == "receivable") & invoices["paid_date"].notna() &
                        (invoices["paid_date"] >= pd.Timestamp(lb_start)) & (invoices["paid_date"] <= pd.Timestamp(as_of))]
        collected = float(paid["amount_paid"].sum())
    base_in = max(0.0, beh_in["revenue"] - collected) + beh_in["other_income"]
    lag = 30
    if not invoices.empty:
        settled = invoices[(invoices["kind"] == "receivable") & invoices["paid_date"].notna()]
        if not settled.empty:
            lag = int(median((settled["paid_date"] - settled["issue_date"]).dt.days.tolist()))
    if collected:
        notes.append(f"Credit sales are modelled separately: open invoices on their expected dates, then new "
                     f"credit-sale collections of ~{fmt(round(collected / days_of_data))}/day from day {lag} "
                     f"(your typical invoice-to-payment time).")

    # Seasonal factor: last year's same month vs last year's average (from monthly sales).
    month_factor: dict[int, float] = {}
    if not txns.empty:
        s = txns[(txns["direction"] == "in") & (txns["category"] == "sales")].copy()
        if not s.empty:
            s["ym"] = s["date"].dt.to_period("M")
            by_m = s.groupby("ym")["amount"].sum()
            if len(by_m) >= 10:
                avg = float(by_m.mean())
                recent_avg = float(by_m.tail(3).mean()) or avg
                for p, v in by_m.items():
                    if p.end_time.date() < as_of - timedelta(days=200):  # roughly "last year"
                        month_factor[p.month] = max(0.5, min(2.0, (float(v) / avg) / max(recent_avg / avg, 0.3)))
                if month_factor:
                    notes.append("Seasonal factors from last year's months are applied to baseline sales.")

    # Scheduled flows: receivables, payables, recurring.
    scheduled: list[Flow] = []
    behav = payment_behavior(invoices) if not invoices.empty else {}
    global_late = median([v["avg_days_late"] for v in behav.values()]) if behav else 0.0
    if not invoices.empty:
        for r in invoices[invoices["status"].isin(["open", "partial"])].itertuples():
            outstanding = float(r.amount) - float(r.amount_paid or 0)
            if outstanding <= 0:
                continue
            due = r.due_date.date()
            if r.kind == "receivable":
                late = behav.get(str(r.counterparty), {}).get("avg_days_late", global_late)
                expected = due + timedelta(days=max(0, int(round(late))))
                overdue_days = (as_of - due).days
                prob = 0.5 if overdue_days > 90 else 1.0
                if expected <= as_of:
                    expected = as_of + timedelta(days=7 if overdue_days <= 60 else 21)
                scheduled.append(Flow(expected, round(outstanding * prob, 2), f"Collection {r.invoice_no or ''} "
                                      f"from {r.counterparty}".strip(), "receivable", ref=f"invoice:{r.id}",
                                      probability=prob, category=str(r.counterparty)))
            else:
                when = due if due > as_of else as_of + timedelta(days=3)
                scheduled.append(Flow(when, -round(outstanding, 2), f"Pay {r.counterparty} {r.invoice_no or ''}".strip(),
                                      "payable", ref=f"invoice:{r.id}", category=str(r.counterparty)))
    for rec in recurring:
        for d in _next_dates(rec, as_of, horizon):
            scheduled.append(Flow(d, -rec.amount, rec.name, "obligation", ref=f"{rec.source}:{rec.category}",
                                  category=rec.category))

    # Volatility of weekly net cash flow (zero days included).
    weekly_std = 0.0
    if not hist.empty:
        signed = hist.assign(s=hist["amount"].where(hist["direction"] == "in", -hist["amount"]))
        daily = signed.groupby(signed["date"].dt.normalize())["s"].sum()
        full = pd.Series(0.0, index=pd.date_range(lb_start, as_of))
        full.update(daily)
        weekly = full.resample("W").sum()
        weekly_std = float(weekly.std(ddof=0)) if len(weekly) > 1 else 0.0

    return ForecastInputs(
        as_of=as_of, horizon=horizon, start_balance=start_balance, base_in_daily=base_in / days_of_data,
        base_collections_daily=collected / days_of_data, collection_lag_days=lag,
        base_out_variable_daily=beh_out["variable"] / days_of_data, base_out_fixed_daily=beh_out["fixed"] / days_of_data,
        month_factor=month_factor, scheduled=scheduled, recurring=recurring, weekly_std=weekly_std,
        low_threshold=float(getattr(business, "low_balance_threshold", 0) or 0), notes=notes,
        trace_rows=hist["id"].tolist() if not hist.empty else [])


# ----------------------------------------------------------------------------- projection
def project(inp: ForecastInputs) -> ForecastResult:
    by_day: dict[date, list[Flow]] = defaultdict(list)
    for f in inp.scheduled:
        by_day[f.day].append(f)
    bal = inp.start_balance
    series: list[DayPoint] = []
    first_neg = first_low = None
    for i in range(1, inp.horizon + 1):
        d = inp.as_of + timedelta(days=i)
        factor = inp.month_factor.get(d.month, 1.0)
        base_in = inp.base_in_daily * factor * inp.revenue_scale
        if i > inp.collection_lag_days:
            base_in += inp.base_collections_daily * factor * inp.revenue_scale
        base_out = inp.base_out_variable_daily * factor * inp.revenue_scale * inp.variable_scale + \
            inp.base_out_fixed_daily + inp.fixed_extra_daily
        sched = by_day.get(d, [])
        s_in = sum(f.amount for f in sched if f.amount > 0)
        s_out = -sum(f.amount for f in sched if f.amount < 0)
        inflow, outflow = base_in + s_in, base_out + s_out
        bal += inflow - outflow
        band = Z80 * inp.weekly_std * math.sqrt(i / 7)
        series.append(DayPoint(date=d, inflow=round(inflow, 2), outflow=round(outflow, 2), net=round(inflow - outflow, 2),
                               balance=round(bal, 2), low=round(bal - band, 2), high=round(bal + band, 2),
                               events=[f"{f.label}: {'+' if f.amount > 0 else '-'}{fmt(abs(f.amount))}" for f in sched]))
        if first_neg is None and bal < 0:
            first_neg = d
        if first_low is None and bal < inp.low_threshold:
            first_low = d

    summaries = []
    for h in (30, 60, 90):
        if h > inp.horizon:
            continue
        part = series[:h]
        mn = min(part, key=lambda p: p.balance)
        summaries.append(HorizonSummary(days=h, end_balance=part[-1].balance,
                                        total_inflow=round(sum(p.inflow for p in part), 2),
                                        total_outflow=round(sum(p.outflow for p in part), 2),
                                        min_balance=mn.balance, min_balance_date=mn.date))
    total_net = sum(p.net for p in series)
    avg_monthly_net = total_net / inp.horizon * 30
    runway = (max(inp.start_balance, 0) / -avg_monthly_net) if avg_monthly_net < 0 else None

    t = Trace(formula="balance[t] = balance[t-1] + baseline inflow - baseline outflow + scheduled items; "
                      "80% band = ±1.28·σ(weekly net)·√(t/7)", period=f"{inp.as_of} + {inp.horizon} days")
    t.step("Starting balance", round(inp.start_balance, 2))
    t.step("Baseline inflow per day", round(inp.base_in_daily, 2), "non-invoice sales + other income, last 90 days")
    t.step("New credit-sale collections per day", round(inp.base_collections_daily, 2),
           f"historical invoice collections, applied after day {inp.collection_lag_days}")
    t.step("Baseline variable outflow per day", round(inp.base_out_variable_daily, 2))
    t.step("Baseline fixed/other outflow per day", round(inp.base_out_fixed_daily, 2))
    t.step("Scheduled inflows (receivables)", round(sum(f.amount for f in inp.scheduled if f.amount > 0), 2))
    t.step("Scheduled outflows (obligations, payables)", round(-sum(f.amount for f in inp.scheduled if f.amount < 0), 2))
    t.step("σ of weekly net cash flow", round(inp.weekly_std, 2))
    for s in summaries:
        t.step(f"Balance in {s.days} days", s.end_balance,
               f"{fmt(inp.start_balance)} + {fmt(s.total_inflow)} - {fmt(s.total_outflow)}")
    t.rows(inp.trace_rows)
    t.assumptions += ["Forecasts are estimates, not guarantees; the shaded band shows a typical 80% range.",
                      "Invoices more than 90 days overdue are counted at 50% (collection risk).",
                      "Customers are assumed to keep paying with their usual delay."]
    sched_items = sorted(({"date": f.day.isoformat(), "amount": f.amount, "label": f.label, "kind": f.kind,
                           "probability": f.probability} for f in inp.scheduled
                          if f.day <= inp.as_of + timedelta(days=inp.horizon)), key=lambda x: x["date"])
    return ForecastResult(
        as_of=inp.as_of, horizon_days=inp.horizon, start_balance=round(inp.start_balance, 2), summaries=summaries,
        first_negative_date=first_neg, first_below_threshold_date=first_low, low_balance_threshold=inp.low_threshold,
        runway_months=round(runway, 1) if runway is not None else None, avg_monthly_net=round(avg_monthly_net, 2),
        scheduled_items=sched_items[:60],
        recurring=[{"name": r.name, "category": r.category, "amount": r.amount, "day_of_month": r.day_of_month,
                    "source": r.source} for r in inp.recurring],
        series=series, notes=inp.notes, trace=t)


def forecast(txns: pd.DataFrame, invoices: pd.DataFrame, obligations: list[Any], business: Any, as_of: date,
             horizon: int = 90) -> ForecastResult:
    return project(build_inputs(txns, invoices, obligations, business, as_of, horizon))
