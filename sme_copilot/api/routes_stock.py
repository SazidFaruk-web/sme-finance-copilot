"""Stock endpoints: items, adjustments, status table, Excel export. Writes to items/stock are owner-only."""
from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from sme_copilot.db import get_db
from sme_copilot.models import Item, ItemBarcode, StockMovement, Transaction, User
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
    sold_this_month: float = Field(0, ge=0, le=1e9)


class BarcodeIn(BaseModel):
    code: str = Field(..., min_length=3, max_length=64)
    item_id: int


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
    fields = body.model_dump()
    sold = fields.pop("sold_this_month")
    it = Item(business_id=user.business_id, **fields)
    # ``opening_qty`` is the count on the shelf today, so a month already sold is added back before that sale
    # is recorded: the shelf count stays the number the owner typed, and days-left gets a rate to work from.
    it.opening_qty = float(it.opening_qty) + sold
    db.add(it)
    db.flush()
    if sold > 0:
        S.add_movement(db, it, -sold, "sale")
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="create_item", tier=1, inputs=body.model_dump(), result={"item_id": it.id}, commit=False)
    db.commit()
    return {"id": it.id, "name": it.name}


@router.delete("/items/{item_id}")
def delete_item(item_id: int, user: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Remove an item the owner no longer stocks, with its movements. Money records are never touched."""
    it = _item(db, user, item_id)
    row = next((r for r in S.stock_rows(db, user.business_id, as_of_today()) if r["id"] == it.id), None)
    name, qty = it.name, (row or {}).get("qty", it.opening_qty)
    moves = db.execute(sa_delete(StockMovement).where(StockMovement.item_id == it.id)).rowcount
    db.delete(it)
    db.flush()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="delete_item", tier=1, inputs={"item_id": item_id},
                 result={"name": name, "qty": qty, "movements": moves}, commit=False)
    db.commit()
    return {"deleted": item_id, "name": name}


@router.get("/stock/barcode")
def scan(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """What a scanner just read. Unknown codes are reported as unknown, never matched to something close."""
    code = code.strip()
    row = db.scalar(select(ItemBarcode).where(ItemBarcode.business_id == user.business_id,
                                              ItemBarcode.code == code))
    if row is None:
        return {"found": False, "code": code, "item": None}
    it = db.get(Item, row.item_id)
    if it is None:
        return {"found": False, "code": code, "item": None}
    stock = next((r for r in S.stock_rows(db, user.business_id, as_of_today()) if r["id"] == it.id), None)
    return {"found": True, "code": code,
            "item": {"id": it.id, "name": it.name, "unit": it.unit, "price": float(it.cost_price or 0),
                     "qty": (stock or {}).get("qty", 0), "status": (stock or {}).get("status", "ok")}}


@router.post("/stock/barcode")
def attach_barcode(body: BarcodeIn, user: User = Depends(require_owner),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    """Teach the app a code once, so every later scan of that product finds it."""
    it = _item(db, user, body.item_id)
    code = body.code.strip()
    existing = db.scalar(select(ItemBarcode).where(ItemBarcode.business_id == user.business_id,
                                                   ItemBarcode.code == code))
    if existing is not None and existing.item_id != it.id:
        other = db.get(Item, existing.item_id)
        raise HTTPException(409, f"that code already belongs to {other.name if other else 'another item'}")
    if existing is None:
        db.add(ItemBarcode(business_id=user.business_id, item_id=it.id, code=code))
        db.flush()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="attach_barcode", tier=1, inputs={"item_id": it.id}, result={"item": it.name}, commit=False)
    db.commit()
    return {"code": code, "item_id": it.id, "name": it.name}


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
