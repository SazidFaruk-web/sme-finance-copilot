"""Home price drawer: public market prices near the business and next-month price direction."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.config import get_settings
from sme_copilot.db import get_db
from sme_copilot.market import service
from sme_copilot.models import Business, HomePrefs, User

from .deps import as_of_today, current_user

router = APIRouter(prefix="/api/market")


@router.get("/prices")
def market_prices(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Read-only public data for every role. Only the business's district and type choose what is shown."""
    if not get_settings().market_prices_enabled:
        raise HTTPException(404, "market prices are turned off on this server")
    business = db.get(Business, user.business_id)
    prefs = db.scalar(select(HomePrefs).where(HomePrefs.user_id == user.id, HomePrefs.business_id == user.business_id))
    return service.overview(business.district if business else None, prefs.business_type if prefs else None,
                            as_of_today())
