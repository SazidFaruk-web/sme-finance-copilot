"""Putting a roadmap together, and keeping it in step with the owner's records."""
from __future__ import annotations

from datetime import date
from typing import Any

from sme_copilot.config import get_settings
from sme_copilot.models import Business

from . import engine, facts as facts_module, narrative, prices
from .goal import Goal, read_goal
from .models import GoalPlan
from .prices import PriceEstimate

MAX_GOALS = 40


def _model_allowed(use_model: bool | None) -> bool:
    """The operator switch decides, unless a caller (a test, a benchmark) states otherwise."""
    return get_settings().goal_roadmap_model if use_model is None else use_model


def _goal_from_row(row: GoalPlan) -> Goal:
    return Goal(text=row.goal_text, item=row.item, specification=row.specification,
                category=row.category, amount=float(row.target_amount) if row.target_amount else None,
                amount_from="owner" if row.price_source == "owner" else "unknown",
                horizon_months=row.horizon_months)


def _price_from_row(row: GoalPlan) -> PriceEstimate:
    detail = dict(row.price_detail or {})
    detail.pop("amount", None)
    return PriceEstimate(amount=float(row.target_amount) if row.target_amount is not None else None,
                         source=row.price_source, **{k: v for k, v in detail.items()
                                                     if k in ("low", "high", "label", "note", "samples", "reviewed")})


def shape_key(plan, strategy: str, language: str) -> str:
    """What the wording depends on. Adjusting a price rarely changes it, so the wording is reused."""
    steps = "|".join(f"{p.kind}:{p.months}:{p.season}" for p in plan.phases)
    return f"{language}/{strategy}/{steps}"


def compose(db, business: Business, row: GoalPlan, today: date, *, language: str = "en",
            use_model: bool | None = None) -> tuple[dict[str, Any], str]:
    """Build the whole roadmap for a stored goal. Returns (plan payload, facts stamp).

    Wording the model already produced is reused while the plan keeps the same shape, so changing a
    price or a monthly amount redraws instantly instead of waiting on another local model run.
    """
    goal = _goal_from_row(row)
    price = _price_from_row(row)
    f = facts_module.gather(db, business, today)
    plan = engine.build(goal, price, f, horizon_months=row.horizon_months,
                        monthly_override=float(row.monthly_override) if row.monthly_override else None,
                        illustrative=get_settings().illustrative_guidance)
    key = shape_key(plan, plan.strategy, language)
    previous = (row.plan or {}).get("narrative") or {}
    if previous.get("shape") == key and previous.get("phases"):
        words = previous
    else:
        words = narrative.write(plan, goal, f, language=language, use_model=_model_allowed(use_model))
        words["shape"] = key

    text_by_index = {p["index"]: p for p in words["phases"]}
    phases = []
    for phase in plan.phases:
        written = text_by_index.get(phase.index, {})
        phases.append({**_phase_dict(phase), "title": written.get("title", ""),
                       "summary": written.get("summary", ""), "actions": written.get("actions", [])})

    payload = {
        "goal": {"text": goal.text, "item": goal.item, "specification": goal.specification,
                 "category": goal.category},
        "price": price.as_dict(),
        "facts": f.as_dict(),
        "plan": {**plan.as_dict(), "phases": phases},
        "narrative": {"headline": words["headline"], "subtitle": words["subtitle"],
                      "written_by": words["written_by"], "language": words["language"],
                      "shape": words.get("shape", ""), "phases": words["phases"]},
        "built_on": today.isoformat(),
    }
    return payload, f.stamp


def _phase_dict(phase: engine.Phase) -> dict[str, Any]:
    return {"index": phase.index, "kind": phase.kind, "from_month": phase.from_month,
            "to_month": phase.to_month, "months": phase.months, "amount": phase.amount,
            "cumulative": phase.cumulative, "share": phase.share, "season": phase.season}


def create(db, business: Business, user, today: date, *, text: str, request_key: str,
           language: str = "en", search_price: bool = False, amount: float | None = None,
           horizon_months: int | None = None, use_model: bool | None = None) -> GoalPlan:
    """Read the owner's sentence, settle on a price, and store the first draft of the roadmap."""
    goal = read_goal(text, language=language, use_model=_model_allowed(use_model))
    estimate = prices.estimate(goal.item, goal.specification,
                               amount=amount if amount is not None else goal.amount,
                               search=search_price)
    row = GoalPlan(business_id=business.id, user_id=user.id, request_key=request_key, status="draft",
                   language=language, goal_text=goal.text, item=goal.item, specification=goal.specification,
                   category=goal.category, target_amount=estimate.amount, price_source=estimate.source,
                   price_detail=_detail(estimate), horizon_months=horizon_months or goal.horizon_months)
    db.add(row)
    db.flush()
    refresh(db, business, row, today, use_model=use_model)
    return row


def _detail(estimate: PriceEstimate) -> dict[str, Any]:
    data = estimate.as_dict()
    data.pop("amount", None)
    data.pop("source", None)
    return data


def refresh(db, business: Business, row: GoalPlan, today: date, *, use_model: bool | None = None) -> GoalPlan:
    """Rebuild the roadmap from the records as they stand now."""
    payload, stamp = compose(db, business, row, today, language=row.language, use_model=use_model)
    row.plan = payload
    row.facts_stamp = stamp
    row.start_month = date.fromisoformat(payload["plan"]["start_month"] + "-01")
    from sme_copilot.models import utcnow

    row.updated_at = utcnow()
    return row


def set_price(db, business: Business, row: GoalPlan, today: date, *, amount: float | None = None,
              search: bool = False, use_model: bool | None = None) -> GoalPlan:
    """Replace the price with the owner's own figure, or with a fresh lookup they asked for."""
    estimate = prices.estimate(row.item, row.specification, amount=amount, search=search)
    row.target_amount = estimate.amount
    row.price_source = estimate.source
    row.price_detail = _detail(estimate)
    return refresh(db, business, row, today, use_model=use_model)


def view(db, business: Business, row: GoalPlan, today: date) -> dict[str, Any]:
    """What the app shows for one goal, including whether the records have moved on since."""
    current = facts_module.gather(db, business, today)
    plan = dict(row.plan or {})
    return {
        "id": row.id, "status": row.status, "language": row.language,
        "request_key": row.request_key,
        "horizon_months": row.horizon_months,
        "monthly_override": float(row.monthly_override) if row.monthly_override else None,
        "progress": row.progress or {"done": []},
        "stale": bool(row.facts_stamp) and row.facts_stamp != current.stamp,
        "price_lookup_available": prices.lookup_available(),
        "updated_at": row.updated_at.isoformat(),
        **plan,
    }


def summary(row: GoalPlan) -> dict[str, Any]:
    """One line per goal, for the Strategy list."""
    plan = (row.plan or {}).get("plan", {})
    words = (row.plan or {}).get("narrative", {})
    return {"id": row.id, "status": row.status, "item": row.item,
            "target": plan.get("target"), "template": plan.get("template"),
            "strategy": plan.get("strategy"), "feasible": plan.get("feasible"),
            "months_needed": plan.get("months_needed"), "buy_month": plan.get("buy_month"),
            "headline": words.get("headline", ""), "updated_at": row.updated_at.isoformat()}
