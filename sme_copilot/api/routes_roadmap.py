"""Goal roadmaps, scoped to one business. Nothing here buys, borrows or sends anything."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sme_copilot.db import get_db
from sme_copilot.models import Business, User
from sme_copilot.roadmap import facts as facts_module, prices, service
from sme_copilot.roadmap.models import GoalPlan
from sme_copilot.security import audit

from .deps import as_of_today, current_user, require_owner, require_tier

router = APIRouter(prefix="/api/strategy", tags=["goal roadmaps"])


def fail(code: str, status: int = 422):
    raise HTTPException(status, {"code": code})


def own(db: Session, user: User, goal_id: int) -> GoalPlan:
    row = db.get(GoalPlan, goal_id)
    if not row or row.business_id != user.business_id:
        fail("not_found", 404)
    return row


def business_of(db: Session, user: User) -> Business:
    b = db.get(Business, user.business_id)
    if b is None:
        fail("not_found", 404)
    return b


@router.get("/goal-context")
def goal_context(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What the planner already knows before the owner types anything."""
    today = as_of_today()
    f = facts_module.gather(db, business_of(db, user), today)
    return {"facts": f.as_dict(), "price_lookup_available": prices.lookup_available(),
            "today": today.isoformat(),
            "can_plan": f.monthly_surplus is not None and f.monthly_surplus > 0 or f.spare_cash > 0}


class CreateGoal(BaseModel):
    text: str = Field(min_length=3, max_length=400)
    request_key: str = Field(min_length=8, max_length=80)
    language: Literal["en", "bn", "zh"] = "en"
    search_price: bool = False       # the owner asked for an online price lookup for this item
    amount: float | None = Field(None, gt=0, le=1e9)
    horizon_months: int | None = Field(None, ge=1, le=60)


@router.post("/goals")
def create_goal(body: CreateGoal, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)):
    existing = db.scalar(select(GoalPlan).where(GoalPlan.business_id == user.business_id,
                                                GoalPlan.request_key == body.request_key))
    if existing:
        return service.view(db, business_of(db, user), existing, as_of_today())
    if db.scalar(select(func.count(GoalPlan.id)).where(GoalPlan.business_id == user.business_id)) >= service.MAX_GOALS:
        fail("too_many_goals")
    business = business_of(db, user)
    row = service.create(db, business, user, as_of_today(), text=body.text, request_key=body.request_key,
                         language=body.language, search_price=body.search_price, amount=body.amount,
                         horizon_months=body.horizon_months)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id,
                 event_type="operation", action="goal_roadmap_created", tier=1,
                 inputs={"goal_id": row.id, "price_source": row.price_source,
                         "looked_up_online": body.search_price}, commit=False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("conflict", 409)
    db.refresh(row)
    return service.view(db, business, row, as_of_today())


@router.get("/goals")
def list_goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(GoalPlan).where(GoalPlan.business_id == user.business_id)
                      .order_by(GoalPlan.updated_at.desc()).limit(service.MAX_GOALS))
    return [service.summary(r) for r in rows]


@router.get("/goals/{goal_id}")
def get_goal(goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.view(db, business_of(db, user), own(db, user, goal_id), as_of_today())


class ChangeGoal(BaseModel):
    amount: float | None = Field(None, gt=0, le=1e9)
    search_price: bool = False
    horizon_months: int | None = Field(None, ge=1, le=60)
    monthly_amount: float | None = Field(None, ge=0, le=1e8)
    language: Literal["en", "bn", "zh"] | None = None
    status: Literal["draft", "saved", "achieved", "dropped"] | None = None
    step_done: int | None = Field(None, ge=1, le=12)
    step_undone: int | None = Field(None, ge=1, le=12)
    rebuild: bool = False


@router.patch("/goals/{goal_id}")
def change_goal(goal_id: int, body: ChangeGoal, user: User = Depends(require_tier(1)),
                db: Session = Depends(get_db)):
    row = own(db, user, goal_id)
    business, today = business_of(db, user), as_of_today()
    rebuild = body.rebuild

    if body.language and body.language != row.language:
        row.language, rebuild = body.language, True
    if body.horizon_months is not None and body.horizon_months != row.horizon_months:
        row.horizon_months, rebuild = body.horizon_months, True
    if body.monthly_amount is not None:
        row.monthly_override = body.monthly_amount or None
        rebuild = True
    if body.status:
        row.status = body.status
    if body.step_done is not None or body.step_undone is not None:
        done = set((row.progress or {}).get("done", []))
        done.add(body.step_done) if body.step_done is not None else None
        done.discard(body.step_undone) if body.step_undone is not None else None
        row.progress = {"done": sorted(done)}

    if body.amount is not None or body.search_price:
        if body.search_price and not prices.lookup_available():
            fail("lookup_unavailable")
        service.set_price(db, business, row, today, amount=body.amount, search=body.search_price)
    elif rebuild:
        service.refresh(db, business, row, today)

    db.commit()
    db.refresh(row)
    return service.view(db, business, row, today)


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    row = own(db, user, goal_id)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id,
                 event_type="operation", action="goal_roadmap_deleted", tier=1,
                 inputs={"goal_id": row.id}, commit=False)
    db.delete(row)
    db.commit()
    return {"deleted": goal_id}
