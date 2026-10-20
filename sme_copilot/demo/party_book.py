"""Demo customers and suppliers, so the side list has people in it before the owner adds their own.

Invented names and contact details for demonstration only: the phone numbers are not issued ranges and the
addresses are example.com. Names already written on the business's own invoices are added first, so their
balances and buying history are real figures from the seeded records rather than decoration; the rest are
name-only, which is the point of the feature - a customer exists because the owner named them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.models import Invoice, Party
from sme_copilot.tools.textnorm import normalize

TARGET = 10  # how many of each kind a demo business ends up with

CUSTOMERS: list[tuple[str, str, str, str]] = [
    ("Saif Telecom (PK)", "01911234569", "saif@example.com", "Buys covers and chargers for resale"),
    ("Nasrin Electronics", "01611234570", "nasrin@example.com", "Pays by bKash, usually on time"),
    ("Chawkbazar Gadget Corner", "01511234571", "chawkbazar@example.com", "Small orders, comes every week"),
    ("Jashim Uddin", "01711234572", "", "Retail customer, buys on credit"),
    ("Khulna Mobile Hut", "01811234573", "khulnahut@example.com", "Out of town, pays on delivery"),
    ("Tahmina Store", "01911234574", "tahmina@example.com", "Screen protectors and earphones"),
    ("Patenga Phone Care", "01611234575", "patenga@example.com", "Repair shop, buys spares"),
    ("Mizan Brothers", "01511234576", "mizan@example.com", "Bulk orders before Eid"),
    ("Rumana Akter", "01711234577", "", "Walk-in who now buys on account"),
    ("Sylhet Mobile Gallery", "01811234578", "sylhetgallery@example.com", "Monthly order, slow to pay"),
]

SUPPLIERS: list[tuple[str, str, str, str]] = [
    ("Bongshal Accessories Mart", "01812345002", "bongshal@example.com", "Covers and cables, 7 day credit"),
    ("Shenzhen Link Imports", "01912345003", "import@example.com", "Imported stock, pays in advance"),
    ("Chattogram Cable House", "01612345004", "cablehouse@example.com", "Charging cables"),
    ("Nahar Packaging", "01512345005", "nahar@example.com", "Boxes and carry bags"),
    ("BD Power Bank Depot", "01712345006", "depot@example.com", "Power banks, minimum 20 pieces"),
    ("Rafiq Transport", "01812345007", "", "Delivery from Dhaka"),
    ("Elite Screen Guard Co", "01912345008", "elite@example.com", "Screen protectors"),
    ("New Market Charger Hub", "01612345009", "chargerhub@example.com", "Fast chargers"),
    ("Hasan Printing Press", "01512345010", "hasan@example.com", "Receipt books and stickers"),
    ("Karnaphuli Battery House", "01712345011", "karnaphuli@example.com", "Batteries, cash only"),
]

BOOK = {"customer": CUSTOMERS, "supplier": SUPPLIERS}
INVOICE_KIND = {"customer": "receivable", "supplier": "payable"}


def _anchors(db: Session, business_id: int, kind: str) -> list[str]:
    """The names this business has already invoiced, newest first: they become the first named parties."""
    seen: dict[str, str] = {}
    for i in db.scalars(select(Invoice).where(Invoice.business_id == business_id,
                                              Invoice.kind == INVOICE_KIND[kind]).order_by(Invoice.issue_date.desc())):
        seen.setdefault(normalize(i.counterparty), i.counterparty.strip())
    return list(seen.values())


def seed_parties(db: Session, business_id: int, kind: str, target: int = TARGET) -> list[Party]:
    """Top this business up to ``target`` named parties of one kind. Existing names are never duplicated."""
    have = {k for p in db.scalars(select(Party).where(Party.business_id == business_id, Party.kind == kind))
            for k in [normalize(p.name), *(normalize(a) for a in (p.aliases or []))]}
    made: list[Party] = []
    wanted = [(n, "", "", "") for n in _anchors(db, business_id, kind)] + BOOK[kind]
    for name, phone, email, note in wanted:
        if len(have) >= target:
            break
        key = normalize(name)
        if not key or key in have:
            continue
        p = Party(business_id=business_id, kind=kind, name=name, aliases=[], phone=phone or None,
                  email=email or None, note=note)
        db.add(p)
        have.add(key)
        made.append(p)
    db.flush()
    return made


def seed_all(db: Session, business_id: int, target: int = TARGET) -> dict[str, int]:
    return {kind: len(seed_parties(db, business_id, kind, target)) for kind in BOOK}
