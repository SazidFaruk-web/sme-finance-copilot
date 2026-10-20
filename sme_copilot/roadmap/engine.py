"""The roadmap itself: how many months, how much each month, and what shape the plan takes.

Every number here comes from the owner's records (``facts``) and the price they confirmed. The month
weighting follows their own recorded busy and quiet months, so a plan asks for more in a month that
has historically earned more. No rate, demand, saving or approval is assumed.

Borrowing is never recommended as a product. When saving alone cannot reach the goal in time, the
plan states how much would have to be borrowed and what repayment the records could carry, and sends
the owner to a lender for a written quote.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from math import ceil
from typing import Any

from sme_copilot.pilot.calculations import money
from sme_copilot.tools.analysis import add_months, month_start

from .facts import Facts
from .goal import Goal
from .prices import PriceEstimate

# How much of a typical month's surplus a plan may ask for. The rest absorbs a slow week.
SAFETY_SHARE = 0.75
# Monthly amounts are rounded down to this, so the plan asks for a figure an owner can hold in mind.
ROUND_TO = 100
MAX_MONTHS = 36
# Beyond this, saving alone is treated as too long for one plan and financing is set out as an option.
SAVE_ONLY_LIMIT = 24
# The share of a typical month's surplus that could service a repayment, if a lender offered one.
REPAYMENT_SHARE = 0.5
# How much of today's spare cash a plan starts with. The rest stays available for the unexpected.
START_SHARE = 0.5
# A repayment longer than this is not a plan, it is a different decision.
MAX_REPAY_MONTHS = 60

TEMPLATES = (
    "quick-win", "two-step", "stepper", "season-bars", "staircase", "quarter-grid",
    "split-rail", "year-bands", "two-track", "milestone-arc", "runway-gauge", "gap-review",
)


@dataclass
class PlanMonth:
    month: str          # YYYY-MM
    amount: float       # to put aside this month
    cumulative: float
    share: float        # of the target, 0..1
    season: str         # peak | normal | low
    events: list[str] = field(default_factory=list)


@dataclass
class Phase:
    index: int
    kind: str           # start | save | borrow | buy | repay | review
    from_month: str
    to_month: str
    months: int
    amount: float       # money moved in this phase
    amount_kind: str    # total | monthly
    cumulative: float
    share: float
    season: str
    title: dict[str, str] = field(default_factory=dict)
    summary: dict[str, str] = field(default_factory=dict)
    actions: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Plan:
    strategy: str       # save_only | save_then_borrow | quick_win | out_of_reach
    template: str
    target: float
    start_month: str
    buy_month: str | None
    months_needed: int
    monthly_amount: float
    from_savings: float
    from_cash_now: float
    to_borrow: float
    repay_capacity: float
    repay_months: int | None
    feasible: bool
    reasons: list[str] = field(default_factory=list)   # reviewed ids, rendered by the UI
    month_plan: list[PlanMonth] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    watchouts: list[str] = field(default_factory=list)  # reviewed ids
    illustrative_finance: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round_down(value: float) -> float:
    return float(max(0, int(value // ROUND_TO) * ROUND_TO))


def seasonal_weights(facts: Facts) -> dict[int, float]:
    """A weight per calendar month, from the owner's own recorded money in.

    1.0 means an average month. Capped so one unusual festival month cannot dominate a plan.
    """
    if not facts.season_known:
        return {}
    by_calendar: dict[int, list[float]] = {}
    for row in facts.months:
        by_calendar.setdefault(int(row.month[5:]), []).append(row.index)
    weights = {m: sum(v) / len(v) for m, v in by_calendar.items() if v}
    return {m: min(1.8, max(0.4, round(w, 2))) for m, w in weights.items()}


def monthly_capacity(facts: Facts, override: float | None = None) -> float:
    """What the plan may ask for in an average month."""
    if override is not None and override > 0:
        return money(override)
    if not facts.monthly_surplus or facts.monthly_surplus <= 0:
        return 0.0
    return _round_down(facts.monthly_surplus * SAFETY_SHARE)


def _schedule(start: date, base: float, weights: dict[int, float], needed: float,
              facts: Facts, limit: int) -> list[PlanMonth]:
    """Month-by-month amounts until ``needed`` is covered, weighted by recorded seasonality."""
    rows: list[PlanMonth] = []
    if base <= 0:
        return rows
    events = {row.month[5:]: row.events for row in facts.months}
    running = 0.0
    cursor = start
    for _ in range(limit):
        weight = weights.get(cursor.month, 1.0)
        amount = _round_down(base * weight) or base
        remaining = round(needed - running, 2)
        if remaining <= 0:
            break
        amount = min(amount, remaining)
        running = round(running + amount, 2)
        rows.append(PlanMonth(
            month=cursor.strftime("%Y-%m"), amount=money(amount), cumulative=money(running),
            share=round(running / needed, 4) if needed else 1.0,
            season="peak" if weight >= 1.2 else "low" if weight <= 0.8 else "normal",
            events=events.get(f"{cursor.month:02d}", [])))
        cursor = add_months(cursor, 1)
        if running >= needed:
            break
    # A last month asking for a few taka reads as a mistake: fold it into the month before.
    if len(rows) > 1 and rows[-1].amount < base * 0.2:
        tail = rows.pop()
        rows[-1].amount = money(rows[-1].amount + tail.amount)
        rows[-1].cumulative = tail.cumulative
        rows[-1].share = tail.share
    return rows


def _group(rows: list[PlanMonth], target_groups: int) -> list[list[PlanMonth]]:
    """Split the months into at most ``target_groups`` runs of similar length."""
    if not rows:
        return []
    size = max(1, ceil(len(rows) / max(1, target_groups)))
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def choose_template(plan: Plan, facts: Facts, goal_horizon: int | None) -> str:
    """One of twelve reviewed layouts. The shape of the plan decides; the model never does."""
    if not plan.feasible:
        return "gap-review"
    if plan.months_needed <= 1:
        return "quick-win"
    if plan.strategy == "save_then_borrow":
        return "split-rail"
    if facts.monthly_surplus is not None and plan.monthly_amount > facts.monthly_surplus * 0.95:
        return "two-track"          # the plan needs more money in, not only tighter spending
    if plan.months_needed == 2:
        return "two-step"
    if plan.from_cash_now >= plan.target * 0.5:
        return "runway-gauge"       # most of it is already there; show how little is left to go
    if goal_horizon and plan.months_needed <= goal_horizon <= 18:
        return "milestone-arc"      # the owner set the date; show the waypoints to it
    if facts.season_known and 3 <= plan.months_needed <= 12:
        return "season-bars"
    if plan.months_needed <= 4:
        return "stepper"
    if plan.months_needed <= 7:
        return "staircase"
    if plan.months_needed <= 12:
        return "quarter-grid"
    return "year-bands"


def _phases(plan: Plan, facts: Facts) -> list[Phase]:
    """Up to five narrative steps. The model later writes their wording, never their figures."""
    phases: list[Phase] = []
    index = 1
    running = plan.from_cash_now

    if plan.from_cash_now > 0:
        phases.append(Phase(index=index, kind="start", from_month=plan.start_month, to_month=plan.start_month,
                            months=0, amount=money(plan.from_cash_now), amount_kind="total", cumulative=money(running),
                            share=round(running / plan.target, 4) if plan.target else 0.0, season="normal"))
        index += 1

    # Four saving steps at most, so a year-long plan still reads as a short list.
    want = 2 if plan.months_needed <= 3 else 3 if plan.months_needed <= 8 else 4
    if plan.strategy == "save_then_borrow":
        want = min(want, 2)
    blocks = _group(plan.month_plan, want)
    if not plan.feasible:
        # Saving towards something unreachable is still worth doing, but one step and a date to
        # look again is an honest plan. Years of steps towards a goal that never arrives is not.
        blocks = _group(plan.month_plan[:6], 1)
    for block in blocks:
        amount = round(sum(m.amount for m in block), 2)
        running = round(running + amount, 2)
        seasons = [m.season for m in block]
        phases.append(Phase(
            index=index, kind="save", from_month=block[0].month, to_month=block[-1].month,
            months=len(block), amount=money(amount), amount_kind="total", cumulative=money(running),
            share=round(running / plan.target, 4) if plan.target else 0.0,
            season="peak" if seasons.count("peak") * 2 >= len(seasons) else
                   "low" if seasons.count("low") * 2 >= len(seasons) else "normal"))
        index += 1

    end_month = plan.month_plan[-1].month if plan.month_plan else plan.start_month
    if plan.strategy == "save_then_borrow" and plan.to_borrow > 0:
        phases.append(Phase(index=index, kind="borrow", from_month=end_month, to_month=end_month, months=0,
                            amount=money(plan.to_borrow), amount_kind="total", cumulative=money(plan.target),
                            share=1.0, season="normal"))
        index += 1
    if plan.feasible and plan.buy_month:
        phases.append(Phase(index=index, kind="buy", from_month=plan.buy_month, to_month=plan.buy_month, months=0,
                            amount=money(plan.target), amount_kind="total", cumulative=money(plan.target),
                            share=1.0, season="normal"))
        index += 1
    if plan.strategy == "save_then_borrow" and plan.repay_months:
        last = add_months(date.fromisoformat(plan.buy_month + "-01"), plan.repay_months)
        phases.append(Phase(index=index, kind="repay", from_month=plan.buy_month, to_month=last.strftime("%Y-%m"),
                            months=plan.repay_months, amount=money(plan.repay_capacity), amount_kind="monthly",
                            cumulative=money(plan.target), share=1.0, season="normal"))
        index += 1
    if not plan.feasible:
        review = add_months(date.fromisoformat(plan.start_month + "-01"), 6).strftime("%Y-%m")
        phases.append(Phase(index=index, kind="review", from_month=review, to_month=review, months=0,
                            amount=0.0, amount_kind="total", cumulative=money(running),
                            share=round(running / plan.target, 4) if plan.target else 0.0, season="normal"))
    return phases


def build(goal: Goal, price: PriceEstimate, facts: Facts, *, horizon_months: int | None = None,
          monthly_override: float | None = None, illustrative: bool = False) -> Plan:
    """The whole roadmap, from a confirmed price and the owner's recorded capacity."""
    today = date.fromisoformat(facts.today)
    start = add_months(month_start(today), 1)   # the plan starts with the next whole month
    target = money(price.amount or 0.0)
    horizon = horizon_months or goal.horizon_months

    from_cash = money(min(facts.spare_cash * START_SHARE, target))
    base = monthly_capacity(facts, monthly_override)
    weights = seasonal_weights(facts)
    needed = money(max(0.0, target - from_cash))

    plan = Plan(strategy="save_only", template="stepper", target=target, start_month=start.strftime("%Y-%m"),
                buy_month=None, months_needed=0, monthly_amount=money(base), from_savings=0.0,
                from_cash_now=from_cash, to_borrow=0.0,
                repay_capacity=money(_round_down((facts.monthly_surplus or 0) * REPAYMENT_SHARE)),
                repay_months=None, feasible=False)

    if target <= 0:
        plan.reasons.append("no_price")
        plan.template = "gap-review"
        plan.phases = _phases(plan, facts)
        return plan

    if needed <= 0:
        plan.strategy, plan.feasible = "quick_win", True
        plan.months_needed, plan.buy_month = 0, start.strftime("%Y-%m")
        plan.month_plan = []
        plan.template = "quick-win"
        plan.phases = _phases(plan, facts)
        plan.watchouts = _watchouts(plan, facts, price)
        return plan

    if base <= 0:
        plan.reasons.append("no_surplus")
        plan.template = "gap-review"
        plan.phases = _phases(plan, facts)
        plan.watchouts = _watchouts(plan, facts, price)
        return plan

    rows = _schedule(start, base, weights, needed, facts, MAX_MONTHS)
    saved = rows[-1].cumulative if rows else 0.0
    plan.month_plan = rows
    plan.months_needed = len(rows)
    plan.from_savings = money(saved)

    reaches_goal = saved >= needed - 0.5
    cap = min(horizon, SAVE_ONLY_LIMIT) if horizon else SAVE_ONLY_LIMIT

    if reaches_goal and plan.months_needed <= cap:
        plan.strategy, plan.feasible = "save_only", True
        plan.buy_month = rows[-1].month
    else:
        # Saving alone is too slow for the deadline. Save what the deadline allows, then set out
        # the shortfall as money that would have to come from somewhere else.
        keep = [r for r in rows[:cap]]
        plan.month_plan = keep
        plan.months_needed = len(keep)
        plan.from_savings = money(keep[-1].cumulative if keep else 0.0)
        shortfall = money(max(0.0, target - from_cash - plan.from_savings))
        plan.to_borrow = shortfall
        affordable = plan.repay_capacity > 0 and shortfall / plan.repay_capacity <= MAX_REPAY_MONTHS
        if affordable and shortfall > 0:
            plan.strategy, plan.feasible = "save_then_borrow", True
            plan.buy_month = keep[-1].month if keep else start.strftime("%Y-%m")
            plan.repay_months = min(60, ceil(shortfall / plan.repay_capacity))
            plan.reasons.append("saving_alone_too_slow")
            if illustrative:
                plan.illustrative_finance = _illustrative_finance(shortfall, plan.repay_months)
        else:
            plan.strategy, plan.feasible = "out_of_reach", False
            plan.reasons.append("repayment_too_large" if shortfall > 0 and plan.repay_capacity > 0 else "out_of_reach")

    plan.template = choose_template(plan, facts, horizon)
    plan.phases = _phases(plan, facts)
    plan.watchouts = _watchouts(plan, facts, price)
    return plan


def _illustrative_finance(amount: float, months: int) -> dict[str, Any]:
    """A demo-only illustration of what such a loan would cost. Never shown to a real owner."""
    from sme_copilot.tools.finance_math import emi_reducing

    low, high = 11.0, 14.0
    return {"amount": money(amount), "months": months, "rate_low_pct": low, "rate_high_pct": high,
            "monthly_low": money(emi_reducing(amount, low, months)),
            "monthly_high": money(emi_reducing(amount, high, months)),
            "illustrative": True, "source": "config/financing/catalog.yaml (unverified placeholder band)"}


def _watchouts(plan: Plan, facts: Facts, price: PriceEstimate) -> list[str]:
    """Reviewed warning ids. The UI holds their wording; the model may not add to this list."""
    out: list[str] = []
    if price.source in ("catalog", "web"):
        out.append("price_is_an_estimate")
    if price.source == "unknown":
        out.append("price_unknown")
    if facts.months_of_history < 3:
        out.append("short_history")
    if facts.bills_to_pay > 0 and facts.bills_to_pay > (facts.monthly_surplus or 0):
        out.append("bills_first")
    if facts.season_known and any(m.season == "low" for m in plan.month_plan):
        out.append("quiet_months")
    if plan.from_cash_now > 0 and facts.reserve > 0:
        out.append("reserve_kept")
    if plan.strategy == "save_then_borrow":
        out.append("quote_before_borrowing")
    if facts.worst_month_surplus is not None and facts.worst_month_surplus < 0:
        out.append("some_months_lost_money")
    return out
