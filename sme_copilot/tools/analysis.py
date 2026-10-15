"""Business financial analysis: deterministic, traceable, unit-tested.

All functions take DataFrames (see tools/repo.py) and return pydantic models that include a
``Trace`` (formula, steps, data rows used). The LLM explains these results; it never computes
them.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from sme_copilot.config import load_yaml

from .categorize import behavior
from .finance_math import coefficient_of_variation, safe_div
from .money import format_bdt
from .trace import Trace, fmt

OPERATING_OUT = ("cogs", "variable", "fixed")


# ----------------------------------------------------------------------------- periods
def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def resolve_period(period: str | None, as_of: date, start: date | None = None,
                   end: date | None = None) -> tuple[date, date, str]:
    """Translate a named period into [start, end] (inclusive) relative to ``as_of``.

    last_N_months means the N most recent *complete* calendar months, so comparisons are clean.
    """
    if start and end:
        return start, end, f"{start.isoformat()} to {end.isoformat()}"
    p = (period or "last_3_months").strip().lower()
    first_this = month_start(as_of)
    if p == "this_month":
        return first_this, as_of, as_of.strftime("%B %Y (to date)")
    if p == "last_month":
        s = add_months(first_this, -1)
        return s, first_this - timedelta(days=1), s.strftime("%B %Y")
    if p.startswith("last_") and p.endswith("_days"):
        n = int(p.split("_")[1])
        return as_of - timedelta(days=n - 1), as_of, f"last {n} days"
    if p.startswith("last_") and p.endswith("_months"):
        n = int(p.split("_")[1])
        s = add_months(first_this, -n)
        e = first_this - timedelta(days=1)
        return s, e, f"{s.strftime('%b %Y')} - {e.strftime('%b %Y')}"
    if p == "ytd":
        return date(as_of.year, 1, 1), as_of, f"Jan-{as_of.strftime('%b %Y')} (year to date)"
    if p in ("fiscal_ytd", "fytd"):
        fy_start = date(as_of.year if as_of.month >= 7 else as_of.year - 1, 7, 1)
        return fy_start, as_of, f"FY from {fy_start.strftime('%b %Y')} (Jul-Jun fiscal year) to date"
    if len(p) == 7 and p[4] == "-":  # YYYY-MM
        y, m = int(p[:4]), int(p[5:])
        s = date(y, m, 1)
        return s, date(y, m, calendar.monthrange(y, m)[1]), s.strftime("%B %Y")
    if p == "all":
        return date(1900, 1, 1), as_of, "all data"
    raise ValueError(f"unknown period '{period}'")


def previous_period(start: date, end: date) -> tuple[date, date]:
    """Equal-length period immediately before [start, end] (month-aligned when possible)."""
    if start.day == 1 and (end + timedelta(days=1)).day == 1:
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        ps = add_months(start, -months)
        return ps, start - timedelta(days=1)
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)


def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]


def _sources(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    out = []
    for src, g in df.groupby("source"):
        rows = sorted(int(r) for r in g["source_row"].dropna().tolist())
        span = f" rows {rows[0]}-{rows[-1]}" if rows else ""
        out.append(f"{src}{span} ({len(g)} txns)")
    return out[:8]


def _add_behavior(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["behavior"] = [("variable" if c == "uncategorized" and d == "out" else behavior(c))
                      for c, d in zip(df["category"], df["direction"])]
    return df


# ----------------------------------------------------------------------------- summary
class CategoryAmount(BaseModel):
    category: str
    amount: float
    share_pct: float
    count: int


class MonthRow(BaseModel):
    month: str
    income: float
    expense: float
    net: float


class SummaryResult(BaseModel):
    period: str
    start: date
    end: date
    total_income: float
    total_expense: float
    net_cash_flow: float
    income_by_category: list[CategoryAmount]
    expense_by_category: list[CategoryAmount]
    monthly: list[MonthRow]
    transaction_count: int
    anomaly_count: int
    trace: Trace


def _by_cat(df: pd.DataFrame, total: float) -> list[CategoryAmount]:
    if df.empty:
        return []
    g = df.groupby("category")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    return [CategoryAmount(category=c, amount=round(float(r["sum"]), 2),
                           share_pct=round(100 * float(r["sum"]) / total, 1) if total else 0.0, count=int(r["count"]))
            for c, r in g.iterrows()]


def monthly_table(df: pd.DataFrame) -> list[MonthRow]:
    if df.empty:
        return []
    d = df.copy()
    d["month"] = d["date"].dt.strftime("%Y-%m")
    piv = d.pivot_table(index="month", columns="direction", values="amount", aggfunc="sum", fill_value=0.0)
    out = []
    for m, r in piv.sort_index().iterrows():
        inc, exp = float(r.get("in", 0.0)), float(r.get("out", 0.0))
        out.append(MonthRow(month=str(m), income=round(inc, 2), expense=round(exp, 2), net=round(inc - exp, 2)))
    return out


def income_expense_summary(txns: pd.DataFrame, start: date, end: date, label: str = "") -> SummaryResult:
    df = _slice(txns, start, end)
    inc = df[df["direction"] == "in"]
    out = df[df["direction"] == "out"]
    ti, te = float(inc["amount"].sum()), float(out["amount"].sum())
    t = Trace(formula="net cash flow = total inflows - total outflows", period=label or f"{start} to {end}")
    t.step("Total inflows", round(ti, 2), f"sum of {len(inc)} inflow rows")
    t.step("Total outflows", round(te, 2), f"sum of {len(out)} outflow rows")
    t.step("Net cash flow", round(ti - te, 2), f"{fmt(ti)} - {fmt(te)}")
    t.rows(df["id"].tolist())
    t.sources = _sources(df)
    t.assumptions.append("Transactions flagged as duplicates are excluded.")
    return SummaryResult(
        period=label or f"{start} to {end}", start=start, end=end, total_income=round(ti, 2),
        total_expense=round(te, 2), net_cash_flow=round(ti - te, 2), income_by_category=_by_cat(inc, ti),
        expense_by_category=_by_cat(out, te), monthly=monthly_table(df), transaction_count=len(df),
        anomaly_count=int(df["is_anomaly"].sum()) if not df.empty else 0, trace=t)


# ----------------------------------------------------------------------------- profitability
class ProfitabilityResult(BaseModel):
    period: str
    revenue: float
    other_income: float
    cogs: float
    gross_profit: float
    gross_margin_pct: float | None
    variable_opex: float
    fixed_opex: float
    operating_profit: float
    net_margin_pct: float | None
    excluded: dict[str, float]
    trace: Trace


def profitability(txns: pd.DataFrame, start: date, end: date, label: str = "") -> ProfitabilityResult:
    df = _add_behavior(_slice(txns, start, end))

    def total(direction: str, beh: str) -> float:
        if df.empty:
            return 0.0
        return float(df[(df["direction"] == direction) & (df["behavior"] == beh)]["amount"].sum())

    revenue, other = total("in", "revenue") - total("out", "contra_revenue"), total("in", "other_income")
    cogs, var, fixed = total("out", "cogs") - total("in", "contra_cogs"), total("out", "variable"), total("out", "fixed")
    gp = revenue - cogs
    op = revenue + other - cogs - var - fixed
    excluded = {
        "loan_repayments_and_financing_out": round(total("out", "financing"), 2),
        "loan_disbursements_in": round(total("in", "financing"), 2),
        "equipment_capex": round(total("out", "capex"), 2),
        "owner_drawings_and_transfers": round(total("out", "non_operating"), 2),
        "owner_capital_in": round(total("in", "non_operating"), 2),
    }
    gm = safe_div(gp, revenue)
    nm = safe_div(op, revenue)
    t = Trace(formula="gross margin = (revenue - COGS) / revenue; net operating margin = operating profit / revenue",
              period=label or f"{start} to {end}")
    t.step("Revenue (sales)", round(revenue, 2))
    t.step("COGS (stock & raw-material purchases)", round(cogs, 2))
    t.step("Gross profit", round(gp, 2), f"{fmt(revenue)} - {fmt(cogs)}")
    t.step("Gross margin %", round(gm * 100, 2) if gm is not None else None,
           f"{fmt(gp)} / {fmt(revenue)} x 100" if revenue else "no revenue")
    t.step("Variable operating costs", round(var, 2))
    t.step("Fixed operating costs", round(fixed, 2))
    t.step("Other income", round(other, 2))
    t.step("Operating profit", round(op, 2), f"{fmt(revenue)} + {fmt(other)} - {fmt(cogs)} - {fmt(var)} - {fmt(fixed)}")
    t.step("Net operating margin %", round(nm * 100, 2) if nm is not None else None,
           f"{fmt(op)} / {fmt(revenue)} x 100" if revenue else "no revenue")
    used = df[df["behavior"].isin(["revenue", "other_income", "contra_revenue", "contra_cogs", *OPERATING_OUT])] if not df.empty else df
    t.rows(used["id"].tolist() if not used.empty else [])
    t.sources = _sources(used) if not used.empty else []
    t.assumptions += [
        "Cash basis: purchases of stock in the period are treated as COGS (no inventory valuation).",
        "Loan repayments (principal + interest), equipment purchases and owner drawings are excluded from "
        "operating profit and shown separately.",
        "Uncategorized outflows are counted as variable operating costs (conservative).",
    ]
    return ProfitabilityResult(
        period=label or f"{start} to {end}", revenue=round(revenue, 2), other_income=round(other, 2),
        cogs=round(cogs, 2), gross_profit=round(gp, 2), gross_margin_pct=round(gm * 100, 2) if gm is not None else None,
        variable_opex=round(var, 2), fixed_opex=round(fixed, 2), operating_profit=round(op, 2),
        net_margin_pct=round(nm * 100, 2) if nm is not None else None, excluded=excluded, trace=t)


# ----------------------------------------------------------------------------- break-even
class BreakEvenResult(BaseModel):
    months_used: int
    avg_monthly_revenue: float
    avg_monthly_fixed_costs: float
    variable_cost_ratio: float | None
    contribution_margin_ratio: float | None
    break_even_monthly_revenue: float | None
    break_even_daily_revenue: float | None
    margin_of_safety_pct: float | None
    status: str
    trace: Trace


def break_even(txns: pd.DataFrame, as_of: date, months: int = 3) -> BreakEvenResult:
    s, e, label = resolve_period(f"last_{months}_months", as_of)
    p = profitability(txns, s, e, label)
    rev_m = p.revenue / months
    fixed_m = p.fixed_opex / months
    var_ratio = safe_div(p.cogs + p.variable_opex, p.revenue)
    t = Trace(formula="break-even revenue = monthly fixed costs / (1 - variable costs / revenue)", period=label)
    t.step("Months averaged", months)
    t.step("Average monthly revenue", round(rev_m, 2), f"{fmt(p.revenue)} / {months}")
    t.step("Average monthly fixed costs", round(fixed_m, 2), f"{fmt(p.fixed_opex)} / {months}")
    t.rows(p.trace.row_ids)
    t.row_count = p.trace.row_count
    t.sources = p.trace.sources
    t.assumptions = p.trace.assumptions + ["Variable costs = COGS + variable operating costs."]
    if var_ratio is None:
        return BreakEvenResult(months_used=months, avg_monthly_revenue=0, avg_monthly_fixed_costs=round(fixed_m, 2),
                               variable_cost_ratio=None, contribution_margin_ratio=None,
                               break_even_monthly_revenue=None, break_even_daily_revenue=None,
                               margin_of_safety_pct=None, status="no_revenue", trace=t)
    cm = 1 - var_ratio
    t.step("Variable cost ratio", round(var_ratio, 4), f"({fmt(p.cogs)} + {fmt(p.variable_opex)}) / {fmt(p.revenue)}")
    t.step("Contribution margin ratio", round(cm, 4), f"1 - {var_ratio:.4f}")
    if cm <= 0:
        return BreakEvenResult(months_used=months, avg_monthly_revenue=round(rev_m, 2),
                               avg_monthly_fixed_costs=round(fixed_m, 2), variable_cost_ratio=round(var_ratio, 4),
                               contribution_margin_ratio=round(cm, 4), break_even_monthly_revenue=None,
                               break_even_daily_revenue=None, margin_of_safety_pct=None,
                               status="variable_costs_exceed_revenue", trace=t)
    be = fixed_m / cm
    mos = (rev_m - be) / rev_m if rev_m else None
    t.step("Break-even monthly revenue", round(be, 2), f"{fmt(fixed_m)} / {cm:.4f}")
    t.step("Margin of safety %", round(mos * 100, 2) if mos is not None else None,
           f"({fmt(rev_m)} - {fmt(be)}) / {fmt(rev_m)} x 100")
    return BreakEvenResult(
        months_used=months, avg_monthly_revenue=round(rev_m, 2), avg_monthly_fixed_costs=round(fixed_m, 2),
        variable_cost_ratio=round(var_ratio, 4), contribution_margin_ratio=round(cm, 4),
        break_even_monthly_revenue=round(be, 2), break_even_daily_revenue=round(be / 30, 2),
        margin_of_safety_pct=round(mos * 100, 2) if mos is not None else None,
        status="above_break_even" if rev_m >= be else "below_break_even", trace=t)


# ----------------------------------------------------------------------------- aging
AGING_BUCKETS = ["not_due", "1-30", "31-60", "61-90", "90+"]


class AgingItem(BaseModel):
    invoice_id: int
    invoice_no: str
    counterparty: str
    outstanding: float
    due_date: date
    days_past_due: int
    bucket: str


class AgingResult(BaseModel):
    kind: str
    as_of: date
    buckets: dict[str, float]
    total_outstanding: float
    overdue_total: float
    overdue_count: int
    by_counterparty: list[dict[str, Any]]
    items: list[AgingItem]
    dso_days: float | None = None
    trace: Trace


def _bucket(days: int) -> str:
    if days <= 0:
        return "not_due"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def aging(invoices: pd.DataFrame, as_of: date, kind: str = "receivable",
          txns: pd.DataFrame | None = None) -> AgingResult:
    df = invoices[(invoices["kind"] == kind) & (invoices["status"].isin(["open", "partial"]))] \
        if not invoices.empty else invoices
    df = df[df["issue_date"] <= pd.Timestamp(as_of)] if not df.empty else df
    items: list[AgingItem] = []
    buckets = {b: 0.0 for b in AGING_BUCKETS}
    for _, r in df.iterrows():
        outstanding = float(r["amount"]) - float(r["amount_paid"] or 0)
        if outstanding <= 0.005:
            continue
        dpd = (as_of - r["due_date"].date()).days
        b = _bucket(dpd)
        buckets[b] += outstanding
        items.append(AgingItem(invoice_id=int(r["id"]), invoice_no=str(r["invoice_no"] or ""),
                               counterparty=str(r["counterparty"]), outstanding=round(outstanding, 2),
                               due_date=r["due_date"].date(), days_past_due=dpd, bucket=b))
    items.sort(key=lambda i: -i.days_past_due)
    total = sum(i.outstanding for i in items)
    overdue = [i for i in items if i.days_past_due > 0]
    by_cp: dict[str, dict[str, Any]] = {}
    for i in items:
        d = by_cp.setdefault(i.counterparty, {"counterparty": i.counterparty, "outstanding": 0.0, "overdue": 0.0,
                                              "max_days_past_due": 0, "invoices": 0})
        d["outstanding"] += i.outstanding
        d["invoices"] += 1
        if i.days_past_due > 0:
            d["overdue"] += i.outstanding
        d["max_days_past_due"] = max(d["max_days_past_due"], i.days_past_due)
    cps = sorted(by_cp.values(), key=lambda d: -d["outstanding"])
    for d in cps:
        d["outstanding"], d["overdue"] = round(d["outstanding"], 2), round(d["overdue"], 2)

    t = Trace(formula="outstanding = invoice amount - amount paid; days past due = as-of date - due date",
              period=f"as of {as_of.isoformat()}")
    for b in AGING_BUCKETS:
        t.step(f"{kind} {b} days", round(buckets[b], 2))
    t.step("Total outstanding", round(total, 2), " + ".join(fmt(buckets[b]) for b in AGING_BUCKETS))
    t.rows([i.invoice_id for i in items], table="invoices")
    dso = None
    if kind == "receivable" and txns is not None and not txns.empty:
        s = as_of - timedelta(days=89)
        sales = _slice(txns, s, as_of)
        sales = sales[(sales["direction"] == "in") & (sales["category"] == "sales")]
        daily = float(sales["amount"].sum()) / 90
        if daily > 0:
            dso = round(total / daily, 1)
            t.step("Days sales outstanding (DSO)", dso, f"{fmt(total)} / ({fmt(float(sales['amount'].sum()))} / 90)")
    return AgingResult(kind=kind, as_of=as_of, buckets={k: round(v, 2) for k, v in buckets.items()},
                       total_outstanding=round(total, 2), overdue_total=round(sum(i.outstanding for i in overdue), 2),
                       overdue_count=len(overdue), by_counterparty=cps, items=items, dso_days=dso, trace=t)


def payment_behavior(invoices: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Per counterparty: average days paid after due date, from settled receivables."""
    out: dict[str, dict[str, float]] = {}
    if invoices.empty:
        return out
    paid = invoices[(invoices["kind"] == "receivable") & invoices["paid_date"].notna()]
    for cp, g in paid.groupby("counterparty"):
        late = [(p - d).days for p, d in zip(g["paid_date"], g["due_date"])]
        out[str(cp)] = {"avg_days_late": round(sum(late) / len(late), 1), "invoices": len(late),
                        "max_days_late": max(late)}
    return out


# ----------------------------------------------------------------------------- cost drivers
class CostDriver(BaseModel):
    category: str
    amount: float
    share_pct: float
    previous_amount: float
    change: float
    change_pct: float | None
    behavior: str


class CostDriversResult(BaseModel):
    period: str
    previous_period: str
    total_expense: float
    drivers: list[CostDriver]
    trace: Trace


def top_cost_drivers(txns: pd.DataFrame, start: date, end: date, label: str = "", top_n: int = 6) -> CostDriversResult:
    ps, pe = previous_period(start, end)
    cur = _slice(txns, start, end)
    prev = _slice(txns, ps, pe)
    cur_out = cur[cur["direction"] == "out"] if not cur.empty else cur
    prev_out = prev[prev["direction"] == "out"] if not prev.empty else prev
    cur_g = cur_out.groupby("category")["amount"].sum() if not cur_out.empty else pd.Series(dtype=float)
    prev_g = prev_out.groupby("category")["amount"].sum() if not prev_out.empty else pd.Series(dtype=float)
    total = float(cur_g.sum())
    drivers = []
    for cat, amt in cur_g.sort_values(ascending=False).head(top_n).items():
        pa = float(prev_g.get(cat, 0.0))
        drivers.append(CostDriver(category=str(cat), amount=round(float(amt), 2),
                                  share_pct=round(100 * float(amt) / total, 1) if total else 0,
                                  previous_amount=round(pa, 2), change=round(float(amt) - pa, 2),
                                  change_pct=round(100 * (float(amt) - pa) / pa, 1) if pa else None,
                                  behavior=behavior(str(cat))))
    t = Trace(formula="share = category outflow / total outflow; change vs the previous equal-length period",
              period=label or f"{start} to {end}")
    t.step("Total outflows", round(total, 2))
    for d in drivers:
        t.step(f"{d.category}", d.amount, f"{d.share_pct}% of total; previous {fmt(d.previous_amount)}")
    t.rows(cur_out["id"].tolist() if not cur_out.empty else [])
    t.sources = _sources(cur_out) if not cur_out.empty else []
    return CostDriversResult(period=label or f"{start} to {end}", previous_period=f"{ps} to {pe}",
                             total_expense=round(total, 2), drivers=drivers, trace=t)


# ----------------------------------------------------------------------------- seasonality
@lru_cache
def bd_calendar() -> dict[str, Any]:
    return load_yaml("calendar_bd.yaml")


def events_for_month(year: int, month: int) -> list[str]:
    """Events whose date, or pre-festival demand window, overlaps the given month."""
    ms = date(year, month, 1)
    me = date(year, month, calendar.monthrange(year, month)[1])
    names = []
    for ev in bd_calendar().get("events", []):
        d = ev["date"] if isinstance(ev["date"], date) else date.fromisoformat(str(ev["date"]))
        window_start = d - timedelta(days=int(ev.get("demand_window_days", 14)))
        if window_start <= me and d >= ms:
            names.append(ev["name"] + (" (approx. date)" if ev.get("approx") else ""))
    for se in bd_calendar().get("seasons", []):
        if month in se.get("months", []):
            names.append(se["name"])
    return names


class SeasonMonth(BaseModel):
    month: str
    revenue: float
    index: float
    label: str  # peak | normal | low
    events: list[str]


class SeasonalityResult(BaseModel):
    months: list[SeasonMonth]
    average_monthly_revenue: float
    peaks: list[str]
    lows: list[str]
    upcoming_events: list[dict[str, Any]]
    revenue_cv: float | None
    insights: list[str]
    trace: Trace


def seasonality(txns: pd.DataFrame, as_of: date, lookback_months: int = 18) -> SeasonalityResult:
    s = add_months(month_start(as_of), -lookback_months)
    e = month_start(as_of) - timedelta(days=1)
    df = _slice(txns, s, e)
    sales = df[(df["direction"] == "in") & (df["category"] == "sales")] if not df.empty else df
    t = Trace(formula="seasonal index = month revenue / average monthly revenue", period=f"{s} to {e}")
    if sales.empty:
        return SeasonalityResult(months=[], average_monthly_revenue=0, peaks=[], lows=[], upcoming_events=[],
                                 revenue_cv=None, insights=["Not enough sales history yet."], trace=t)
    sales = sales.copy()
    sales["month"] = sales["date"].dt.strftime("%Y-%m")
    by_m = sales.groupby("month")["amount"].sum().sort_index()
    avg = float(by_m.mean())
    months, peaks, lows, insights = [], [], [], []
    for m, rev in by_m.items():
        y, mo = int(m[:4]), int(m[5:])
        idx = float(rev) / avg if avg else 0
        lbl = "peak" if idx >= 1.2 else "low" if idx <= 0.8 else "normal"
        evs = events_for_month(y, mo)
        months.append(SeasonMonth(month=m, revenue=round(float(rev), 2), index=round(idx, 2), label=lbl, events=evs))
        if lbl == "peak":
            peaks.append(m)
            festive = [x for x in evs if "Eid" in x or "Puja" in x or "Boishakh" in x]
            why = f" - matches {', '.join(festive)}" if festive else (f" - season: {evs[0]}" if evs else "")
            insights.append(f"{date(y, mo, 1).strftime('%B %Y')} revenue was {round((idx - 1) * 100)}% above your "
                            f"monthly average{why}.")
        elif lbl == "low":
            lows.append(m)
            insights.append(f"{date(y, mo, 1).strftime('%B %Y')} revenue was {round((1 - idx) * 100)}% below average"
                            + (f" ({evs[0]})." if evs else "."))
        t.step(f"{m} index", round(idx, 2), f"{fmt(float(rev))} / {fmt(avg)}")
    t.step("Average monthly revenue", round(avg, 2), f"mean of {len(by_m)} months")
    t.rows(sales["id"].tolist())
    t.sources = _sources(sales)
    t.assumptions.append("Festival dates in config/calendar_bd.yaml are approximate and only used to explain patterns.")

    upcoming = []
    hist = {sm.month: sm for sm in months}
    for ev in bd_calendar().get("events", []):
        d = ev["date"] if isinstance(ev["date"], date) else date.fromisoformat(str(ev["date"]))
        if as_of <= d <= as_of + timedelta(days=120):
            prior = [x for x in bd_calendar()["events"] if x["name"] == ev["name"] and
                     (x["date"] if isinstance(x["date"], date) else date.fromisoformat(str(x["date"]))) < as_of]
            uplift = None
            if prior:
                pd_ = prior[-1]["date"] if isinstance(prior[-1]["date"], date) else date.fromisoformat(str(prior[-1]["date"]))
                key = (pd_ - timedelta(days=10)).strftime("%Y-%m")
                if key in hist:
                    uplift = round((hist[key].index - 1) * 100)
            upcoming.append({"event": ev["name"], "date": d.isoformat(), "approx": bool(ev.get("approx")),
                             "days_away": (d - as_of).days, "last_year_uplift_pct": uplift})
    for u in upcoming:
        if u["last_year_uplift_pct"] and u["last_year_uplift_pct"] > 10:
            insights.append(f"{u['event']} is ~{u['days_away']} days away; last time your sales were "
                            f"{u['last_year_uplift_pct']}% above average around it - plan stock and cash early.")
    cv = coefficient_of_variation([float(v) for v in by_m.values])
    return SeasonalityResult(months=months, average_monthly_revenue=round(avg, 2), peaks=peaks, lows=lows,
                             upcoming_events=upcoming, revenue_cv=round(cv, 3) if cv is not None else None,
                             insights=insights, trace=t)


# ----------------------------------------------------------------------------- explain change
class ChangeDriver(BaseModel):
    category: str
    direction: str
    previous: float
    current: float
    change: float
    effect_on_net: float  # + helps net cash flow, - hurts it


class ExplainChangeResult(BaseModel):
    current_period: str
    previous_period: str
    revenue_change: float
    expense_change: float
    net_change: float
    current_net: float
    previous_net: float
    drivers: list[ChangeDriver]
    customer_changes: list[dict[str, Any]]
    explanation: list[str]
    trace: Trace


def explain_change(txns: pd.DataFrame, start: date, end: date, label: str = "",
                   style: str = "lakh") -> ExplainChangeResult:
    ps, pe = previous_period(start, end)
    cur, prev = _slice(txns, start, end), _slice(txns, ps, pe)

    def totals(df: pd.DataFrame) -> dict[tuple[str, str], float]:
        if df.empty:
            return {}
        return {(c, d): float(v) for (c, d), v in df.groupby(["category", "direction"])["amount"].sum().items()}

    ct, pt = totals(cur), totals(prev)
    drivers = []
    for key in set(ct) | set(pt):
        c, p = ct.get(key, 0.0), pt.get(key, 0.0)
        if abs(c - p) < 0.5:
            continue
        sign = 1 if key[1] == "in" else -1
        drivers.append(ChangeDriver(category=key[0], direction=key[1], previous=round(p, 2), current=round(c, 2),
                                    change=round(c - p, 2), effect_on_net=round(sign * (c - p), 2)))
    drivers.sort(key=lambda d: -abs(d.effect_on_net))

    def side(t: dict, d: str) -> float:
        return sum(v for (_, dd), v in t.items() if dd == d)

    cur_net = side(ct, "in") - side(ct, "out")
    prev_net = side(pt, "in") - side(pt, "out")
    rev_change = ct.get(("sales", "in"), 0.0) - pt.get(("sales", "in"), 0.0)
    exp_change = side(ct, "out") - side(pt, "out")
    net_change = cur_net - prev_net

    # Customer-level revenue changes (who bought more / less)
    cust = []
    if not cur.empty or not prev.empty:
        def by_cp(df):
            s = df[(df["direction"] == "in") & (df["category"] == "sales") & (df["counterparty"] != "")] \
                if not df.empty else df
            return s.groupby("counterparty")["amount"].sum().to_dict() if not s.empty else {}
        cc, pc = by_cp(cur), by_cp(prev)
        for cp in set(cc) | set(pc):
            delta = cc.get(cp, 0.0) - pc.get(cp, 0.0)
            if abs(delta) >= 1:
                cust.append({"counterparty": cp, "previous": round(pc.get(cp, 0.0), 2),
                             "current": round(cc.get(cp, 0.0), 2), "change": round(delta, 2)})
        cust.sort(key=lambda x: -abs(x["change"]))
        cust = cust[:5]

    f = lambda v: format_bdt(abs(v), style=style)  # noqa: E731
    lines = [f"Net cash flow {'rose' if net_change >= 0 else 'fell'} by {f(net_change)} "
             f"(from {format_bdt(prev_net, style=style)} to {format_bdt(cur_net, style=style)})."]
    for d in drivers[:4]:
        verb = ("up" if d.change > 0 else "down")
        what = "income" if d.direction == "in" else "spending"
        impact = "helped" if d.effect_on_net > 0 else "hurt"
        lines.append(f"{d.category.replace('_', ' ').title()} {what} {verb} {f(d.change)} "
                     f"({format_bdt(d.previous, style=style)} -> {format_bdt(d.current, style=style)}), which {impact} "
                     f"net cash flow.")
    for c in cust[:2]:
        lines.append(f"Sales from {c['counterparty']} {'increased' if c['change'] > 0 else 'decreased'} by "
                     f"{f(c['change'])}.")
    if any(d.category == "inventory" and d.change > 0 for d in drivers[:3]) and rev_change < 0:
        lines.append("You bought more stock while sales fell - check for slow-moving inventory tying up cash.")

    t = Trace(formula="change = current period total - previous period total, per category",
              period=f"{label or f'{start} to {end}'} vs {ps} to {pe}")
    t.step("Current net cash flow", round(cur_net, 2))
    t.step("Previous net cash flow", round(prev_net, 2))
    t.step("Change in net cash flow", round(net_change, 2), f"{fmt(cur_net)} - {fmt(prev_net)}")
    for d in drivers[:6]:
        t.step(f"{d.category} ({d.direction})", d.change, f"{fmt(d.current)} - {fmt(d.previous)}")
    ids = (cur["id"].tolist() if not cur.empty else []) + (prev["id"].tolist() if not prev.empty else [])
    t.rows(ids)
    return ExplainChangeResult(
        current_period=label or f"{start} to {end}", previous_period=f"{ps} to {pe}",
        revenue_change=round(rev_change, 2), expense_change=round(exp_change, 2), net_change=round(net_change, 2),
        current_net=round(cur_net, 2), previous_net=round(prev_net, 2), drivers=drivers[:10],
        customer_changes=cust, explanation=lines, trace=t)


# ----------------------------------------------------------------------------- metrics for lending
class BusinessMetrics(BaseModel):
    as_of: date
    months_of_data: int
    business_age_months: int | None
    avg_monthly_revenue_6m: float
    avg_monthly_revenue_12m: float
    revenue_cv_12m: float | None
    avg_monthly_operating_cash_flow_6m: float
    existing_monthly_debt_service: float
    existing_dscr: float | None
    gross_margin_pct_6m: float | None
    net_margin_pct_6m: float | None
    receivables_overdue: float
    collateral_value: float
    has_trade_license: bool
    has_tin: bool
    has_bank_account: bool
    vat_registered: bool
    women_led: bool
    sector: str
    trace: Trace


def business_metrics(txns: pd.DataFrame, invoices: pd.DataFrame, business: Any, as_of: date) -> BusinessMetrics:
    s6, e6, l6 = resolve_period("last_6_months", as_of)
    s12, e12, _ = resolve_period("last_12_months", as_of)
    p6 = profitability(txns, s6, e6, l6)
    df12 = _slice(txns, s12, e12)
    monthly = [m.income for m in monthly_table(df12[(df12["direction"] == "in") & (df12["category"] == "sales")])] \
        if not df12.empty else []
    rev12 = sum(monthly) / 12 if monthly else 0.0
    cv = coefficient_of_variation(monthly) if len(monthly) >= 3 else None
    months_of_data = 0
    if not txns.empty:
        first = txns["date"].min().date()
        months_of_data = (as_of.year - first.year) * 12 + as_of.month - first.month
    age = None
    if getattr(business, "established_on", None):
        eo = business.established_on
        age = (as_of.year - eo.year) * 12 + as_of.month - eo.month
    op_cf = p6.operating_profit / 6
    existing_ds = float(business.existing_monthly_debt_service or 0)
    if existing_ds == 0 and not txns.empty:
        rep = _slice(txns, s6, e6)
        rep = rep[(rep["direction"] == "out") & (rep["category"] == "loan_repayment")]
        existing_ds = float(rep["amount"].sum()) / 6 if not rep.empty else 0.0
    ex_dscr = safe_div(op_cf, existing_ds) if existing_ds else None
    ag = aging(invoices, as_of, "receivable") if not invoices.empty else None
    t = Trace(formula="DSCR = average monthly operating cash flow / monthly debt service; "
                      "revenue CV = std / mean of monthly sales", period=l6)
    t.step("Average monthly operating cash flow (6m)", round(op_cf, 2), f"{fmt(p6.operating_profit)} / 6")
    t.step("Existing monthly debt service", round(existing_ds, 2))
    t.step("Existing DSCR", round(ex_dscr, 2) if ex_dscr else None,
           f"{fmt(op_cf)} / {fmt(existing_ds)}" if existing_ds else "no existing debt")
    t.step("Average monthly revenue (12m)", round(rev12, 2))
    t.step("Revenue CV (12m)", round(cv, 3) if cv is not None else None)
    t.rows(p6.trace.row_ids)
    t.row_count = p6.trace.row_count
    t.sources = p6.trace.sources
    return BusinessMetrics(
        as_of=as_of, months_of_data=months_of_data, business_age_months=age,
        avg_monthly_revenue_6m=round(p6.revenue / 6, 2), avg_monthly_revenue_12m=round(rev12, 2),
        revenue_cv_12m=round(cv, 3) if cv is not None else None, avg_monthly_operating_cash_flow_6m=round(op_cf, 2),
        existing_monthly_debt_service=round(existing_ds, 2), existing_dscr=round(ex_dscr, 2) if ex_dscr else None,
        gross_margin_pct_6m=p6.gross_margin_pct, net_margin_pct_6m=p6.net_margin_pct,
        receivables_overdue=ag.overdue_total if ag else 0.0, collateral_value=float(business.collateral_value or 0),
        has_trade_license=bool(business.has_trade_license), has_tin=bool(business.has_tin),
        has_bank_account=bool(business.has_bank_account), vat_registered=bool(business.vat_registered),
        women_led=bool(business.women_led), sector=business.sector or "", trace=t)
