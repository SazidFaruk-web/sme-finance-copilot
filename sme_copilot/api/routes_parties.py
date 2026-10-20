"""Named customers and suppliers: the side list, one party's details, and matching a written name to a party.

Matching is deterministic (rapidfuzz over names and confirmed aliases), so it works with no model installed.
A close-but-not-exact name is only ever a suggestion: the owner answers "is this him?" and their answer is
stored as a locked link, which later matching never overrides.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.db import get_db
from sme_copilot.models import Invoice, Party, User
from sme_copilot.security import audit
from sme_copilot.tools import parties as P

from .deps import as_of_today, current_user, require_owner

router = APIRouter(prefix="/api")

Kind = Literal["customer", "supplier"]


class PartyIn(BaseModel):
    kind: Kind = "customer"
    name: str = Field(..., min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    note: str = Field("", max_length=500)


class PartyPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    note: str | None = Field(None, max_length=500)


class LinkIn(BaseModel):
    """The owner's own answer about which party an invoice belongs to. ``party_id`` None takes the link away."""
    invoice_id: int
    party_id: int | None = None
    remember_spelling: bool = True


def _party(db: Session, user: User, party_id: int) -> Party:
    p = db.get(Party, party_id)
    if p is None or p.business_id != user.business_id:
        raise HTTPException(404, "party not found")
    return p


def _invoice(db: Session, user: User, invoice_id: int) -> Invoice:
    i = db.get(Invoice, invoice_id)
    if i is None or i.business_id != user.business_id:
        raise HTTPException(404, "invoice not found")
    return i


@router.get("/parties")
def list_parties(kind: Kind = "customer", user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    today = as_of_today()
    rows = P.rows(db, user.business_id, kind, today)
    return {"kind": kind, "as_of": today.isoformat(), "rows": rows,
            "named": sum(1 for r in rows if r["named"]),
            "total_balance": round(sum(r["balance"] for r in rows), 2),
            "total_overdue": round(sum(r["overdue"] for r in rows), 2)}


@router.post("/parties")
def create_party(body: PartyIn, user: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Name a customer or supplier. From here on they exist whether or not an invoice mentions them."""
    hit = P.match(db, user.business_id, body.kind, body.name)
    if hit and hit["exact"]:
        raise HTTPException(409, f"{hit['party'].name} is already on your list")
    p = Party(business_id=user.business_id, kind=body.kind, name=body.name.strip(), aliases=[],
              phone=body.phone or None, email=body.email or None, note=body.note)
    db.add(p)
    db.flush()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="create_party", tier=1, inputs=body.model_dump(exclude={"phone", "email"}),
                 result={"party_id": p.id, "kind": p.kind}, commit=False)
    db.commit()
    return P.detail(db, user.business_id, p, as_of_today())


@router.get("/parties/{party_id}")
def party_detail(party_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    return P.detail(db, user.business_id, _party(db, user, party_id), as_of_today())


@router.patch("/parties/{party_id}")
def update_party(party_id: int, body: PartyPatch, user: User = Depends(require_owner),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    p = _party(db, user, party_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(p, field, value.strip() if isinstance(value, str) else value)
    db.flush()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="update_party", tier=1, inputs={"party_id": party_id,
                                                        "fields": sorted(body.model_dump(exclude_none=True))},
                 result={"name": p.name}, commit=False)
    db.commit()
    return P.detail(db, user.business_id, p, as_of_today())


@router.delete("/parties/{party_id}")
def delete_party(party_id: int, user: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Take a party off the list. Their invoices stay exactly as they are and still show under the written name."""
    p = _party(db, user, party_id)
    name = p.name
    db.delete(p)
    db.flush()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="delete_party", tier=1, inputs={"party_id": party_id}, result={"name": name}, commit=False)
    db.commit()
    return {"deleted": party_id, "name": name}


@router.get("/parties/match/lookup")
def lookup(name: str, kind: Kind = "customer", user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> dict[str, Any]:
    """Is this written name someone already on the list? Exact says yes; close only ever suggests."""
    hit = P.match(db, user.business_id, kind, name)
    if hit is None:
        return {"exact": False, "suggestion": None}
    p = hit["party"]
    return {"exact": hit["exact"],
            "suggestion": {"id": p.id, "name": p.name, "score": hit["score"], "phone": p.phone}}


@router.put("/parties/link")
def set_link(body: LinkIn, user: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    """The owner says which party an invoice belongs to. Stored locked, so matching never changes it back."""
    inv = _invoice(db, user, body.invoice_id)
    if body.party_id is None:
        P.unlink(db, inv.id)
        result: dict[str, Any] = {"invoice_id": inv.id, "party_id": None}
    else:
        p = _party(db, user, body.party_id)
        if P.KIND_OF[p.kind] != inv.kind:
            raise HTTPException(422, "that invoice belongs to the other side of the book")
        P.link(db, inv.id, p.id, locked=True)
        if body.remember_spelling:
            P.remember_alias(db, p, inv.counterparty)
        result = {"invoice_id": inv.id, "party_id": p.id, "name": p.name}
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="link_party", tier=1, inputs=body.model_dump(), result=result, commit=False)
    db.commit()
    return result
