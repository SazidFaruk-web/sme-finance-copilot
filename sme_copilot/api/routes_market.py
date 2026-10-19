"""Home price drawer: public market prices near the business and next-month price direction."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.config import get_settings
from sme_copilot.db import get_db
from sme_copilot.market import catalog, service, watch
from sme_copilot.models import Business, HomePrefs, MarketWatch, User
from sme_copilot.security import audit

from .deps import as_of_today, current_user

router = APIRouter(prefix="/api/market")


def _enabled() -> None:
    if not get_settings().market_prices_enabled:
        raise HTTPException(404, "market prices are turned off on this server")


def _context(db: Session, user: User) -> tuple[Business | None, HomePrefs | None, MarketWatch | None]:
    business = db.get(Business, user.business_id)
    prefs = db.scalar(select(HomePrefs).where(HomePrefs.user_id == user.id, HomePrefs.business_id == user.business_id))
    row = db.scalar(select(MarketWatch).where(MarketWatch.user_id == user.id, MarketWatch.business_id == user.business_id))
    return business, prefs, row


def _suggest(business: Business | None, prefs: HomePrefs | None) -> dict[str, Any]:
    bt = prefs.business_type if prefs else None
    text = bt.split(":", 1)[1] if bt and bt.startswith("other:") else ""
    return watch.suggest(business.name if business else "", bt, text)


def _save(db: Session, user: User, row: MarketWatch | None, items: list[str], source: str, reason: str = "") -> MarketWatch:
    if row is None:
        row = MarketWatch(user_id=user.id, business_id=user.business_id)
        db.add(row)
    row.items, row.source, row.reason = items, source, reason
    db.commit()
    return row


def _watch_out(row: MarketWatch) -> dict[str, Any]:
    return {"items": list(row.items or []), "source": row.source, "reason": row.reason}


@router.get("/prices")
def market_prices(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Read-only public data for every role. The owner's own item list (first picked by the AI Assistant from the
    business name and type) and the district choose what is shown."""
    _enabled()
    business, prefs, row = _context(db, user)
    if row is None:  # first open: ask the AI Assistant once, keep its pick so later opens are instant
        pick = _suggest(business, prefs)
        row = _save(db, user, None, pick["items"], pick["source"], pick["reason"])
    out = service.overview(business.district if business else None, prefs.business_type if prefs else None,
                           as_of_today(), list(row.items or []))
    about = (business.prefs or {}).get("about", "") if business else ""
    if row.source != "owner" and catalog.goods_without_prices(business.name if business else "", about):
        out = {**out, "note": catalog.NO_PRICE_NOTE}
    return {**out, "watch": _watch_out(row)}


@router.get("/items")
def market_items(user: User = Depends(current_user)) -> dict[str, Any]:
    """Every published item an owner can add to their list (for the "Add an item" search)."""
    _enabled()
    return {"items": watch.catalog_rows()}


class ItemsIn(BaseModel):
    items: list[str] = Field(..., max_length=watch.MAX_ITEMS)


@router.put("/items")
def save_items(body: ItemsIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """The owner adds or removes items. Only published items are kept; nothing else is stored."""
    _enabled()
    allowed = watch.available()
    unknown = [i for i in body.items if i not in allowed]
    if unknown:
        raise HTTPException(422, f"no public price for: {', '.join(unknown[:3])}")
    _, _, row = _context(db, user)
    before = list(row.items or []) if row else []
    row = _save(db, user, row, watch.clean(body.items, allowed), "owner")
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="update_price_list", tier=0, inputs={"items": row.items}, result={"before": before})
    return _watch_out(row)


@router.post("/items/suggest")
def resuggest(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Ask the AI Assistant again (e.g. after the owner changed the business type); replaces the list."""
    _enabled()
    business, prefs, row = _context(db, user)
    pick = _suggest(business, prefs)
    return _watch_out(_save(db, user, row, pick["items"], pick["source"], pick["reason"]))
