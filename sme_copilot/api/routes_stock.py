"""Stock endpoints: items, adjustments, status table, Excel export. Writes to items/stock are owner-only."""
from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.db import get_db
from sme_copilot.models import Item, Transaction, User
from sme_copilot.security import audit
from sme_copilot.tools import stock as S
from sme_copilot.tools.textnorm import normalize

from .deps import as_of_today, current_user, require_owner, require_tier

router = APIRouter(prefix="/api")


class ItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    unit: str = Field("pcs", max_length=20)
    opening_qty: float = Field(0, ge=0, le=1e9)
    reorder_level: float = Field(0, ge=0, le=1e9)
    cost_price: float = Field(0, ge=0, le=1e9)


class AdjustIn(BaseModel):
    item_id: int
    qty_change: float = Field(..., le=1e9, ge=-1e9)
    reason: str = Field("adjust", max_length=30)


class LinkIn(BaseModel):
    transaction_id: int
    item_id: int
    quantity: float | None = Field(None, gt=0, le=1e9)


def _item(db: Session, user: User, item_id: int) -> Item:
    it = db.get(Item, item_id)
    if it is None or it.business_id != user.business_id:
        raise HTTPException(404, "item not found")
    return it


@router.get("/stock")
def get_stock(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": S.stock_rows(db, user.business_id, as_of_today())}


@router.post("/items")
def create_item(body: ItemIn, user: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    names = {normalize(i.name) for i in db.scalars(select(Item).where(Item.business_id == user.business_id))}
    if normalize(body.name) in names:
        raise HTTPException(409, "an item with this name already exists")
    it = Item(business_id=user.business_id, **body.model_dump())
    db.add(it)
    db.flush()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="create_item", tier=1, inputs=body.model_dump(), result={"item_id": it.id}, commit=False)
    db.commit()
    return {"id": it.id, "name": it.name}


@router.post("/stock/adjust")
def adjust(body: AdjustIn, user: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.qty_change == 0:
        raise HTTPException(422, "qty_change must not be zero")
    it = _item(db, user, body.item_id)
    S.add_movement(db, it, body.qty_change, "adjust")
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="adjust_stock", tier=1, inputs=body.model_dump(), result={"item": it.name}, commit=False)
    db.commit()
    return next(r for r in S.stock_rows(db, user.business_id, as_of_today()) if r["id"] == it.id)


@router.post("/stock/link")
def link(body: LinkIn, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Answer 'Which item?' for a saved transaction."""
    t = db.get(Transaction, body.transaction_id)
    if t is None or t.business_id != user.business_id:
        raise HTTPException(404, "transaction not found")
    it = _item(db, user, body.item_id)
    rtype = S.txn_type(t)
    qty = body.quantity or t.quantity
    if rtype is None or not qty or qty <= 0:
        raise HTTPException(422, "transaction has no stock-relevant type or quantity")
    S.reverse_for_transaction(db, t.id)  # re-linking replaces any earlier link
    S.add_movement(db, it, S.MOVE_SIGN[rtype] * qty, rtype, t.id)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="link_stock", tier=1, inputs=body.model_dump(), result={"item": it.name}, commit=False)
    db.commit()
    return {"linked": True, "item": it.name}


def _cell(v: Any) -> Any:
    """openpyxl turns strings starting with '=' into live formulas: neutralise spreadsheet formula injection."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


@router.get("/stock/export")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock"
    ws.append(["Item", "Unit", "Sold 30d", "Remaining", "Days left", "Reorder level", "Status"])
    for r in S.stock_rows(db, user.business_id, as_of_today()):
        ws.append([_cell(r["name"]), _cell(r["unit"]), r["sold_30d"], r["qty"], r["days_left"], r["reorder_level"],
                   r["status"]])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="stock.xlsx"'})
