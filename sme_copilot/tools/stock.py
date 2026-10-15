"""Stock: append-only movements, deterministic item matching (no LLM), status / days-left, restock cost."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sme_copilot.models import Item, StockMovement, Transaction

from .textnorm import normalize

FUZZY_CUTOFF = 85
LOW_DAYS = 7
# record type -> sign of the stock movement
MOVE_SIGN = {"sale": -1, "sale_return": 1, "purchase": 1, "purchase_return": -1}


def txn_type(t: Transaction) -> str | None:
    """Stock-relevant type of a stored transaction, from direction + category."""
    if t.direction == "in":
        return {"sales": "sale", "purchase_returns": "purchase_return"}.get(t.category)
    return {"sales_returns": "sale_return", "inventory": "purchase"}.get(t.category)


def match_item(session: Session, business_id: int, name: str | None) -> Item | None:
    """Exact name/alias first, then rapidfuzz >= 85. Ambiguous or missing -> None (never guess)."""
    q = normalize(name or "")
    if not q:
        return None
    items = session.scalars(select(Item).where(Item.business_id == business_id)).all()
    keys = [(normalize(k), it) for it in items for k in [it.name, *(it.aliases or [])] if normalize(k)]
    exact = {it.id: it for k, it in keys if k == q}
    if exact:
        return next(iter(exact.values())) if len(exact) == 1 else None
    best: dict[int, tuple[float, Item]] = {}
    for k, it in keys:
        s = fuzz.ratio(q, k)
        if s >= FUZZY_CUTOFF and s > best.get(it.id, (0, it))[0]:
            best[it.id] = (s, it)
    ranked = sorted(best.values(), key=lambda x: -x[0])
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None
    return ranked[0][1]


def add_movement(session: Session, item: Item, qty_change: float, reason: str, transaction_id: int | None = None):
    m = StockMovement(item_id=item.id, qty_change=float(qty_change), reason=reason, transaction_id=transaction_id)
    session.add(m)
    session.flush()
    return m


def item_choices(session: Session, business_id: int) -> list[dict[str, Any]]:
    return [{"id": i.id, "name": i.name, "unit": i.unit}
            for i in session.scalars(select(Item).where(Item.business_id == business_id).order_by(Item.name))]


def link_transaction(session: Session, business_id: int, txn_id: int, rtype: str, item_name: str | None,
                     qty: float | None) -> dict[str, Any]:
    """Create the movement for a saved transaction. Never guesses: no match / no quantity -> ask_item."""
    if rtype not in MOVE_SIGN:
        return {"linked": False, "ask_item": False}
    it = match_item(session, business_id, item_name) if qty and qty > 0 else None
    if it is None:
        return {"linked": False, "ask_item": True, "transaction_id": txn_id, "quantity": qty,
                "suggested_name": item_name or "", "items": item_choices(session, business_id)}
    add_movement(session, it, MOVE_SIGN[rtype] * qty, rtype, txn_id)
    return {"linked": True, "ask_item": False, "item_id": it.id, "item": it.name}


def reverse_for_transaction(session: Session, txn_id: int) -> int:
    """Append reversal rows for the net movement of a transaction (call on delete / re-link / edit)."""
    rows = session.scalars(select(StockMovement).where(StockMovement.transaction_id == txn_id)).all()
    net: dict[tuple[int, str], float] = {}
    for m in rows:
        key = (m.item_id, m.reason.removeprefix("reversal:"))
        net[key] = net.get(key, 0.0) + m.qty_change
    n = 0
    for (item_id, base), q in net.items():
        if abs(q) > 1e-9:
            session.add(StockMovement(item_id=item_id, qty_change=-q, reason=f"reversal:{base}", transaction_id=txn_id))
            n += 1
    session.flush()
    return n


def status_for(qty: float, reorder_level: float, days_left: float | None) -> str:
    if qty <= 0:
        return "out"
    if qty <= reorder_level or (days_left is not None and days_left <= LOW_DAYS):
        return "low"
    return "ok"


def stock_rows(session: Session, business_id: int, as_of: date) -> list[dict[str, Any]]:
    items = session.scalars(select(Item).where(Item.business_id == business_id).order_by(Item.name)).all()
    since = datetime.combine(as_of - timedelta(days=30), datetime.min.time())
    out = []
    for it in items:
        moved = session.scalar(select(func.coalesce(func.sum(StockMovement.qty_change), 0.0))
                               .where(StockMovement.item_id == it.id)) or 0.0
        recent = session.scalars(select(StockMovement).where(StockMovement.item_id == it.id,
                                                             StockMovement.created_at >= since)).all()
        sold = max(0.0, -sum(m.qty_change for m in recent
                             if m.reason.removeprefix("reversal:") in ("sale", "sale_return")))
        qty = it.opening_qty + moved
        days = round(qty / (sold / 30), 1) if sold > 0 and qty > 0 else (0.0 if sold > 0 else None)
        out.append({"id": it.id, "name": it.name, "unit": it.unit, "qty": round(qty, 3), "sold_30d": round(sold, 3),
                    "days_left": days, "reorder_level": it.reorder_level, "cost_price": float(it.cost_price or 0),
                    "status": status_for(qty, it.reorder_level, days)})
    return out


def restock_cost(rows: list[dict[str, Any]]) -> float:
    return round(sum(max(0.0, 2 * r["reorder_level"] - r["qty"]) * r["cost_price"]
                     for r in rows if r["status"] in ("low", "out")), 2)


def relink_after_edit(session: Session, t: Transaction) -> None:
    """A transaction's category/type changed: reverse its movement and re-apply it with the new sign (same item)."""
    first = session.scalar(select(StockMovement).where(StockMovement.transaction_id == t.id)
                           .order_by(StockMovement.id).limit(1))
    if first is None:
        return
    reverse_for_transaction(session, t.id)
    rtype = txn_type(t)
    it = session.get(Item, first.item_id)
    if rtype and t.quantity and t.quantity > 0 and it is not None:
        add_movement(session, it, MOVE_SIGN[rtype] * t.quantity, rtype, t.id)
