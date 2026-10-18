"""Onboarding wizard + per-user home layout (widgets, sidebar, style). Scoped to the caller's own business."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot import home_layout as hl
from sme_copilot.db import get_db
from sme_copilot.models import HomePrefs, User
from sme_copilot.security import audit

from .deps import current_user

router = APIRouter(prefix="/api/home")


def _own_business(user: User, business_id: int | None) -> None:
    if business_id is not None and business_id != user.business_id:
        raise HTTPException(403, "not your business")


def _row(db: Session, user: User) -> HomePrefs | None:
    return db.scalar(select(HomePrefs).where(HomePrefs.user_id == user.id, HomePrefs.business_id == user.business_id))


def _out(p: HomePrefs | None) -> dict[str, Any]:
    if p is None:
        return {"exists": False, **hl.normalize_prefs(business_type=None, mode="general")}
    return {"exists": p.business_type is not None, "business_type": p.business_type, "mode": p.mode,
            "widgets": hl.clean_ids(p.widgets, hl.WIDGET_IDS, len(hl.WIDGET_IDS)), "nav": hl.clean_nav(p.nav, p.business_type),
            "style": p.style if p.style in hl.STYLES else hl.LEGACY_STYLES.get(p.style, "general")}


@router.get("/registry")
def registry(user: User = Depends(current_user)) -> dict[str, Any]:
    return {"widgets": hl.WIDGETS, "nav": hl.NAV, "nav_required": list(hl.NAV_REQUIRED), "business_types": hl.BUSINESS_TYPES,
            "service_types": sorted(hl.SERVICE_TYPES), "simplified": hl.SIMPLIFIED}


@router.get("/prefs")
def get_prefs(business_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    _own_business(user, business_id)
    return _out(_row(db, user))


class SuggestIn(BaseModel):
    business_type: str = Field(..., max_length=40)
    text: str = Field("", max_length=200)  # untrusted free text (only used for "other")


@router.post("/suggest")
def suggest(body: SuggestIn, user: User = Depends(current_user)) -> dict[str, Any]:
    out = hl.suggest_layouts(body.business_type, body.text if body.business_type == "other" else "")
    return {**out, "simplified": hl.SIMPLIFIED, "general": hl.WIDGET_IDS}


class PrefsIn(BaseModel):
    business_id: int | None = None
    business_type: str | None = Field(None, max_length=40)
    text: str = Field("", max_length=200)
    mode: Literal["general", "simplified", "custom"] | None = None
    widgets: list[str] | None = Field(None, max_length=40)
    nav: list[str] | None = Field(None, max_length=40)
    style: Literal["general", "sky", "classic"] | None = None


@router.post("/prefs")
def save_prefs(body: PrefsIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Save the wizard result, or change one field (e.g. style). Any role can set their own home; audited."""
    _own_business(user, body.business_id)
    row = _row(db, user)
    before = _out(row)
    bt = hl.type_key(body.business_type, body.text) if body.business_type else (row.business_type if row else None)
    merged = hl.normalize_prefs(
        business_type=bt,
        mode=body.mode or (row.mode if row else "general"),
        widgets=body.widgets if body.widgets is not None else (row.widgets if row else None),
        nav=body.nav if body.nav is not None else (row.nav if row and body.business_type is None else None),
        style=body.style or (row.style if row else "general"))
    if row is None:
        row = HomePrefs(user_id=user.id, business_id=user.business_id)
        db.add(row)
    for k, v in merged.items():
        setattr(row, k, v)
    db.commit()
    after = _out(row)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="update_home_layout", tier=0,
                 inputs={k: after[k] for k in after if after[k] != before.get(k)},
                 result={"before": {k: before.get(k) for k in after if after[k] != before.get(k)}})
    return after


class SetupIn(BaseModel):
    about: str = Field("", max_length=200)  # untrusted: what the owner says the business sells or does
    business_type: str | None = Field(None, max_length=40)  # optional pick from the list; the owner's choice wins
    style: Literal["general", "sky", "classic"] | None = None


@router.post("/setup")
def setup(body: SetupIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """First-run question. The AI Assistant reads the answer and sets the business type, a short description
    (also the AI Assistant's context) and the market prices to follow; the guided Simple home is used."""
    from sme_copilot.business_profile import profile
    from sme_copilot.models import Business, MarketWatch

    business = db.get(Business, user.business_id)
    out = profile(business.name if business else "", body.about, body.business_type)
    bt = hl.type_key(out["business_type"], out["summary"] or body.about)
    row = _row(db, user)
    before = _out(row)
    merged = hl.normalize_prefs(business_type=bt, mode="simplified", widgets=hl.SIMPLIFIED, nav=None,
                                style=body.style or (row.style if row else "general"))
    if row is None:
        row = HomePrefs(user_id=user.id, business_id=user.business_id)
        db.add(row)
    for k, v in merged.items():
        setattr(row, k, v)
    if business is not None and user.role == "owner":  # the business description belongs to the owner
        business.prefs = {**(business.prefs or {}), "about": hl.clean_text(body.about, 200), "profile_source": out["source"]}
        business.sector = (out["summary"] or hl.BUSINESS_TYPES[hl.base_type(bt)])[:80]
    watch_row = db.scalar(select(MarketWatch).where(MarketWatch.user_id == user.id, MarketWatch.business_id == user.business_id))
    if watch_row is None:
        watch_row = MarketWatch(user_id=user.id, business_id=user.business_id)
        db.add(watch_row)
    watch_row.items, watch_row.source, watch_row.reason = out["price_items"], out["source"], out["summary"]
    db.commit()
    after = _out(row)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="business_setup", tier=0,
                 inputs={"business_type": bt, "source": out["source"], "price_items": out["price_items"]},
                 result={"before": {k: before.get(k) for k in ("business_type", "mode")}})
    return {**after, "summary": out["summary"], "source": out["source"], "price_items": out["price_items"],
            "type_label": hl.BUSINESS_TYPES[hl.base_type(bt)]}


@router.get("/insights")
def insights(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Unusual facts from the owner's own records for Home's occasional note. Read-only, every role."""
    from sme_copilot.home_insight import candidates

    from .deps import as_of_today
    return {"items": candidates(db, user.business_id, as_of_today()), "as_of": as_of_today().isoformat()}
