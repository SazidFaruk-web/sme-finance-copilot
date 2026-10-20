"""Customers and suppliers as records of their own: naming, deterministic matching, and the figures per party.

A party exists because the owner named it, not because an invoice mentioned it. Every invoice still stores the
name it was written with; a ``PartyLink`` says which party that name turned out to be. Matching is rapidfuzz
over names and confirmed aliases, never a language model, so the list keeps working with no model installed
(design contract: the app must remain useful without one). Every figure here is counted from stored invoices.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.models import Invoice, Party, PartyLink

from .textnorm import normalize

FUZZY_CUTOFF = 85       # close spellings only, and never a guess between two equally close names
MIN_QUERY = 3           # below this a fragment would be close to half the names on the list
KIND_OF = {"customer": "receivable", "supplier": "payable"}
REGULAR_DAYS = 45       # a longer gap than this is not a habit worth calling regular


def outstanding(i: Invoice) -> float:
    return round(float(i.amount) - float(i.amount_paid or 0), 2)


def counted(i: Invoice) -> bool:
    """Drafts and written-off invoices do not create a balance owed."""
    return i.status not in ("draft", "written_off")


def score(written: str, known: str) -> float:
    """How alike two names are, written the way an owner writes them.

    People shorten names in a hurry: "shanto" for Shanto Chicken, "kazir" for Kazir Bazar Fish & Meat. Plain
    character similarity punishes that badly (shanto vs shanto chicken scores 60), so a whole-word subset
    counts for as much as a close spelling. Short fragments match nothing, and two names that come out equally
    close are still treated as ambiguous by the caller rather than guessed between.
    """
    if len(written) < MIN_QUERY or len(known) < MIN_QUERY:
        return 0.0
    return max(fuzz.ratio(written, known), fuzz.token_set_ratio(written, known))


def keys(p: Party) -> list[str]:
    return [k for k in [normalize(p.name), *(normalize(a) for a in (p.aliases or []))] if k]


def parties_of(db: Session, business_id: int, kind: str) -> list[Party]:
    return list(db.scalars(select(Party).where(Party.business_id == business_id, Party.kind == kind)
                           .order_by(Party.name)))


def match(db: Session, business_id: int, kind: str, name: str | None) -> dict[str, Any] | None:
    """Exact name/alias first, then rapidfuzz >= 85. Two equally close names are ambiguous -> None (never guess)."""
    q = normalize(name or "")
    if not q:
        return None
    people = parties_of(db, business_id, kind)
    exact = [p for p in people if q in keys(p)]
    if exact:
        return {"party": exact[0], "score": 100.0, "exact": True} if len(exact) == 1 else None
    best: dict[int, tuple[float, Party]] = {}
    for p in people:
        for k in keys(p):
            s = score(q, k)
            if s >= FUZZY_CUTOFF and s > best.get(p.id, (0.0, p))[0]:
                best[p.id] = (s, p)
    ranked = sorted(best.values(), key=lambda x: -x[0])
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None
    return {"party": ranked[0][1], "score": round(ranked[0][0], 1), "exact": False}


def link(db: Session, invoice_id: int, party_id: int, locked: bool) -> PartyLink:
    """Point an invoice at a party. ``locked`` records that the owner chose it, so matching leaves it alone."""
    row = db.scalar(select(PartyLink).where(PartyLink.invoice_id == invoice_id))
    if row is None:
        row = PartyLink(invoice_id=invoice_id, party_id=party_id, locked=locked)
        db.add(row)
    else:
        row.party_id, row.locked = party_id, locked
    db.flush()
    return row


def unlink(db: Session, invoice_id: int) -> None:
    row = db.scalar(select(PartyLink).where(PartyLink.invoice_id == invoice_id))
    if row is not None:
        db.delete(row)
        db.flush()


def remember_alias(db: Session, party: Party, spelling: str) -> None:
    """A confirmed "yes, this is him" teaches the spelling, so the same name matches outright next time."""
    q = normalize(spelling or "")
    if not q or q in keys(party):
        return
    party.aliases = [*(party.aliases or []), spelling.strip()]
    db.flush()


def invoices_of(db: Session, business_id: int, kind: str) -> list[Invoice]:
    return list(db.scalars(select(Invoice).where(Invoice.business_id == business_id,
                                                 Invoice.kind == KIND_OF[kind])))


def resolve(db: Session, business_id: int, kind: str) -> dict[int, int]:
    """invoice id -> party id for this kind: the owner's own link first, then an exact name or alias match."""
    people = parties_of(db, business_id, kind)
    by_key: dict[str, int] = {}
    for p in people:
        for k in keys(p):
            by_key.setdefault(k, p.id)
    links = {r.invoice_id: r.party_id
             for r in db.scalars(select(PartyLink).join(Party, Party.id == PartyLink.party_id)
                                 .where(Party.business_id == business_id, Party.kind == kind))}
    out: dict[int, int] = {}
    for i in invoices_of(db, business_id, kind):
        pid = links.get(i.id) or by_key.get(normalize(i.counterparty))
        if pid:
            out[i.id] = pid
    return out


def _blank(name: str) -> dict[str, Any]:
    return {"name": name, "invoices": 0, "invoiced": 0.0, "paid": 0.0, "balance": 0.0, "overdue": 0.0, "dates": []}


def _add(fig: dict[str, Any], i: Invoice, today: date) -> None:
    owed = outstanding(i)
    fig["invoices"] += 1
    fig["invoiced"] += float(i.amount)
    fig["paid"] += float(i.amount_paid or 0)
    fig["balance"] += owed
    if owed > 0.005 and i.due_date < today:
        fig["overdue"] += owed
    fig["dates"].append(i.issue_date)


def _close(fig: dict[str, Any]) -> dict[str, Any]:
    """Turn the collected dates into how often they come, and round the money."""
    dates = sorted(fig.pop("dates"))
    fig["first_date"] = dates[0].isoformat() if dates else None
    fig["last_date"] = dates[-1].isoformat() if dates else None
    fig["every_days"] = round((dates[-1] - dates[0]).days / (len(dates) - 1), 1) if len(dates) > 1 else None
    fig["regular"] = bool(fig["every_days"] is not None and fig["every_days"] <= REGULAR_DAYS)
    for k in ("invoiced", "paid", "balance", "overdue"):
        fig[k] = round(fig[k], 2)
    return fig


def rows(db: Session, business_id: int, kind: str, today: date) -> list[dict[str, Any]]:
    """The side list: every named party, plus any invoice name not on the list yet, so nothing is hidden."""
    people = {p.id: p for p in parties_of(db, business_id, kind)}
    linked = resolve(db, business_id, kind)
    figs = {pid: _blank(p.name) for pid, p in people.items()}
    unnamed: dict[str, dict[str, Any]] = {}
    for i in invoices_of(db, business_id, kind):
        if not counted(i):
            continue
        pid = linked.get(i.id)
        if pid in figs:
            _add(figs[pid], i, today)
        else:
            _add(unnamed.setdefault(normalize(i.counterparty), _blank(i.counterparty)), i, today)
    out = []
    for pid, fig in figs.items():
        p = people[pid]
        out.append({**_close(fig), "id": pid, "named": True, "phone": p.phone, "email": p.email, "note": p.note})
    for fig in unnamed.values():
        out.append({**_close(fig), "id": None, "named": False, "phone": None, "email": None, "note": ""})
    return sorted(out, key=lambda r: (-r["balance"], r["name"].lower()))


def detail(db: Session, business_id: int, party: Party, today: date) -> dict[str, Any]:
    """One party's facts, all counted from stored invoices: what is owed, what they bought, how often they come."""
    linked = resolve(db, business_id, party.kind)
    fig = _blank(party.name)
    for i in invoices_of(db, business_id, party.kind):
        if counted(i) and linked.get(i.id) == party.id:
            _add(fig, i, today)
    out = _close(fig)
    out.update({"id": party.id, "kind": party.kind, "name": party.name, "phone": party.phone, "email": party.email,
                "note": party.note, "aliases": list(party.aliases or []), "named": True,
                "owes_me": out["balance"] if party.kind == "customer" else 0.0,
                "i_owe": out["balance"] if party.kind == "supplier" else 0.0})
    return out


def next_number(db: Session, business_id: int, kind: str) -> str:
    """A simple running number per kind, continuing past whatever the books already hold."""
    prefix = "INV" if kind == "customer" else "BILL"
    n = len([i for i in invoices_of(db, business_id, kind) if (i.invoice_no or "").startswith(prefix)])
    while True:
        n += 1
        no = f"{prefix}-{n:04d}"
        if not db.scalar(select(Invoice.id).where(Invoice.business_id == business_id, Invoice.invoice_no == no)):
            return no


def invoice_for_entry(db: Session, business_id: int, party: Party, *, amount: float, when: date, description: str,
                      quantity: float | None = None, paid: bool = True) -> Invoice:
    """Turn a recorded sale or purchase into an invoice against a named party, linked and locked to them.

    Only entries whose name is already on the owner's list reach here, so recording "sold 10 biriyani to Saif"
    keeps that customer's total bought, balance and how-often figures right without inventing a debt: a sale
    that was paid at the counter is stored as an already-paid invoice.
    """
    from sme_copilot.models import InvoiceLine

    inv = Invoice(business_id=business_id, kind=KIND_OF[party.kind], invoice_no=next_number(db, business_id, party.kind),
                  counterparty=party.name, amount=round(float(amount), 2),
                  amount_paid=round(float(amount), 2) if paid else 0.0, issue_date=when,
                  due_date=when if paid else when + timedelta(days=30), paid_date=when if paid else None,
                  status="paid" if paid else "open", notes=description[:1000], source="entry")
    db.add(inv)
    db.flush()
    db.add(InvoiceLine(invoice_id=inv.id, description=description[:200] or party.name,
                       quantity=quantity or 1, rate=round(float(amount), 2) / (quantity or 1)))
    link(db, inv.id, party.id, locked=True)
    db.flush()
    return inv


def resolve_entry_party(db: Session, business_id: int, kind: str, written: str | None, party_id: int | None,
                        declined: bool) -> tuple[Party | None, dict[str, Any] | None]:
    """Who a quick entry is for: (party to file it under, question to ask first).

    An exact name files itself. A close name is never assumed: it comes back as a question for the owner,
    and their answer arrives as ``party_id`` (yes) or ``declined`` (no, keep it as written).
    """
    if declined:
        return None, None
    if party_id is not None:
        p = db.get(Party, party_id)
        if p is None or p.business_id != business_id or p.kind != kind:
            raise ValueError("that name is not on your list")
        return p, None
    hit = match(db, business_id, kind, written)
    if hit is None:
        return None, None
    if hit["exact"]:
        return hit["party"], None
    p = hit["party"]
    return None, {"id": p.id, "name": p.name, "score": hit["score"], "written": (written or "").strip(), "kind": kind}


def file_under_party(db: Session, business_id: int, party: Party, entry: Any) -> dict[str, Any]:
    """File a stored entry under a named party: an invoice in their name, so their totals stay right."""
    when = entry.txn_date if isinstance(entry.txn_date, date) else date.fromisoformat(entry.txn_date)
    inv = invoice_for_entry(db, business_id, party, amount=float(entry.amount), when=when,
                            description=entry.description or entry.item or party.name,
                            quantity=entry.quantity, paid=True)
    remember_alias(db, party, entry.counterparty)
    return {"id": party.id, "name": party.name, "kind": party.kind, "invoice_id": inv.id, "invoice_no": inv.invoice_no}
