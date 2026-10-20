"""Demo customers, suppliers and stock that match what the business actually sells.

A kitchen should not open with a supplier called "Shenzhen Link Imports", so each business picks a book from
its own name and description: food, electronics, books or clothing, with a general fallback. Everything here
is invented for demonstration: the phone numbers are outside issued ranges and the addresses are example.com.

Stock is seeded with real movement history (a purchase every week or so, sales most days), so "sold in 30
days", "remaining" and "days left" are counted from stored rows rather than written in as decoration.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.models import Invoice, Item, ItemBarcode, Party, PartyLink, StockMovement
from sme_copilot.tools.textnorm import normalize

TARGET = 10          # named customers and suppliers per business
HISTORY_DAYS = 75    # how far back the seeded stock movements go

# name, phone, email, note
FOOD_CUSTOMERS = [
    ("Saif Ahmed", "01711900101", "saif@example.com", "Orders biryani most Fridays"),
    ("Office lunch - Sylhet IT Park", "01811900102", "lunch@example.com", "Weekday lunch boxes, pays monthly"),
    ("Nusrat Jahan", "01911900103", "", "Family orders, pays by bKash"),
    ("Amberkhana Tuition Centre", "01611900104", "amberkhana@example.com", "Snacks for evening batches"),
    ("Shahana Begum", "01511900105", "", "Pitha orders in winter"),
    ("Hotel Sunrise (staff meals)", "01711900106", "sunrise@example.com", "Staff lunch, 20 plates"),
    ("Rupa Akter", "01811900107", "", "Weekend orders"),
    ("Subhanighat Office Canteen", "01911900108", "canteen@example.com", "Bulk order, pays late"),
    ("Tareq Mahmud", "01611900109", "", "Party orders, pays cash"),
    ("Zindabazar Community Hall", "01511900110", "hall@example.com", "Event catering"),
]
FOOD_SUPPLIERS = [
    ("Bondor Bazar Chicken House", "01712900201", "", "Chicken, delivered every other day"),
    ("Kazir Bazar Fish & Meat", "01812900202", "kazirbazar@example.com", "Beef and fish, cash only"),
    ("Sylhet Rice Mill", "01912900203", "ricemill@example.com", "Chinigura rice by the sack"),
    ("Modhuban Grocery", "01612900204", "modhuban@example.com", "Spices, oil and sugar"),
    ("Taltola Vegetable Supply", "01512900205", "", "Vegetables, every morning"),
    ("Milk Vita Agent - Sylhet", "01712900206", "milkvita@example.com", "Milk and cream"),
    ("Foil Box & Packaging", "01812900207", "packaging@example.com", "Boxes, bags and foil trays"),
    ("Gas Cylinder Service", "01912900208", "", "Cooking gas, two cylinders a month"),
    ("Rasel (delivery rider)", "01612900209", "", "Paid per delivery"),
    ("Sylhet Sweet Supply", "01512900210", "sweets@example.com", "Sweets for event orders"),
]
# name, unit, price, typical quantity sold per day
FOOD_STOCK = [
    ("Chicken biryani", "plate", 220, 12), ("Chicken fry", "piece", 120, 10),
    ("Beef tehari", "plate", 260, 6), ("Vegetable pitha", "piece", 25, 20),
    ("Samosa", "piece", 15, 30), ("Firni", "cup", 60, 8),
    ("Chicken (raw)", "kg", 320, 6), ("Chinigura rice", "kg", 135, 8),
]

ELECTRONICS_CUSTOMERS = [
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
ELECTRONICS_SUPPLIERS = [
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
ELECTRONICS_STOCK = [
    ("Phone cover", "piece", 180, 14), ("Charging cable", "piece", 150, 10),
    ("Fast charger", "piece", 450, 5), ("Earphones", "piece", 320, 6),
    ("Screen protector", "piece", 90, 18), ("Power bank", "piece", 1250, 2),
    ("Bluetooth speaker", "piece", 1600, 1), ("Phone stand", "piece", 140, 4),
]

BOOK_CUSTOMERS = [
    ("Saiful Islam (student)", "01711800101", "", "Buys guide books each term"),
    ("RU Hall Common Room", "01811800102", "hall@example.com", "Newspapers and magazines"),
    ("Nabila Rahman", "01911800103", "", "Novels, pays cash"),
    ("Padma Coaching Centre", "01611800104", "padma@example.com", "Bulk guide books"),
    ("Shohag Stationers", "01511800105", "shohag@example.com", "Resells pens and khata"),
    ("Mehedi Hasan", "01711800106", "", "Textbooks on credit"),
    ("Rajshahi Model School", "01811800107", "school@example.com", "Term orders, pays late"),
    ("Farzana Yeasmin", "01911800108", "", "Children's books"),
    ("Boalia Tuition Home", "01611800109", "boalia@example.com", "Exam papers"),
    ("Kazla Book Club", "01511800110", "club@example.com", "Monthly novel order"),
]
BOOK_SUPPLIERS = [
    ("Banglabazar Book House", "01712800201", "banglabazar@example.com", "Textbooks, 15 day credit"),
    ("Panjeree Distributor", "01812800202", "panjeree@example.com", "Guide books"),
    ("Rajshahi Paper Mart", "01912800203", "", "Khata and paper"),
    ("Matrix Pen Agency", "01612800204", "matrix@example.com", "Pens and markers"),
    ("Anonna Prokashoni", "01512800205", "anonna@example.com", "Novels"),
    ("Sabuj Printing", "01712800206", "", "Exam papers and photocopy"),
    ("Dhaka Courier Service", "01812800207", "", "Delivery from Dhaka"),
    ("Shikkha Stationery", "01912800208", "shikkha@example.com", "School supplies"),
    ("Nobin Plastic Cover", "01612800209", "", "Book covers"),
    ("Rajshahi Gift Corner", "01512800210", "gift@example.com", "Cards and gift items"),
]
BOOK_STOCK = [
    ("HSC Physics guide", "copy", 420, 4), ("Class 9 Math textbook", "copy", 260, 5),
    ("Khata (200 page)", "piece", 75, 15), ("Ball pen", "piece", 12, 40),
    ("Novel - Bengali", "copy", 350, 3), ("Exam paper set", "set", 180, 6),
    ("Geometry box", "piece", 220, 2), ("A4 paper ream", "ream", 480, 1),
]

CLOTH_CUSTOMERS = [
    ("Karim Knit Composite", "01711700101", "karim@example.com", "Garment accessories on credit"),
    ("Shapla Apparels", "01811700102", "shapla@example.com", "Monthly order, pays by bank"),
    ("Saiful Garments", "01911700103", "", "Zippers and buttons"),
    ("Mirpur Tailors", "01611700104", "", "Small orders, cash"),
    ("Nabila Boutique", "01511700105", "nabila@example.com", "Thread and trims"),
    ("Dhaka Fashion House", "01711700106", "fashion@example.com", "Bulk before Eid"),
    ("Rupali Knitwear", "01811700107", "rupali@example.com", "Pays late"),
    ("Alam Textiles", "01911700108", "", "Regular weekly order"),
    ("Shamim Tailoring", "01611700109", "", "Retail customer"),
    ("Uttara Garments Ltd", "01511700110", "uttara@example.com", "Large orders, 30 day terms"),
]
CLOTH_SUPPLIERS = [
    ("Dhaka Zipper House", "01712700201", "zipper@example.com", "Zippers, 15 day credit"),
    ("Lalbagh Thread Mills", "01812700202", "thread@example.com", "Thread by the cone"),
    ("Islampur Button Mart", "01912700203", "", "Buttons and hooks"),
    ("Narayanganj Fabric Co", "01612700204", "fabric@example.com", "Fabric rolls"),
    ("Elastic & Tape Depot", "01512700205", "", "Elastic and tape"),
    ("Label Print House", "01712700206", "labels@example.com", "Care labels and tags"),
    ("Poly Bag Supplier", "01812700207", "", "Packing bags"),
    ("Chittagong Import Agent", "01912700208", "agent@example.com", "Imported trims"),
    ("Keraniganj Transport", "01612700209", "", "Delivery service"),
    ("Sadarghat Needle Store", "01512700210", "", "Needles and tools"),
]
CLOTH_STOCK = [
    ("Zipper 8 inch", "piece", 14, 60), ("Button (shirt)", "dozen", 35, 25),
    ("Sewing thread", "cone", 95, 12), ("Elastic tape", "metre", 18, 30),
    ("Care label", "piece", 3, 80), ("Hook and eye", "dozen", 28, 10),
    ("Poly bag", "piece", 4, 50), ("Shoulder pad", "pair", 22, 8),
]

BOOKS = {
    "food": {"customers": FOOD_CUSTOMERS, "suppliers": FOOD_SUPPLIERS, "stock": FOOD_STOCK},
    "electronics": {"customers": ELECTRONICS_CUSTOMERS, "suppliers": ELECTRONICS_SUPPLIERS, "stock": ELECTRONICS_STOCK},
    "books": {"customers": BOOK_CUSTOMERS, "suppliers": BOOK_SUPPLIERS, "stock": BOOK_STOCK},
    "clothing": {"customers": CLOTH_CUSTOMERS, "suppliers": CLOTH_SUPPLIERS, "stock": CLOTH_STOCK},
}
DEFAULT_BOOK = "clothing"

# First match wins, so the longer words come before the broad ones.
KEYWORDS = [
    ("food", ("kitchen", "biryani", "biriyani", "restaurant", "cafe", "catering", "cake", "bakery", "food",
              "hotel", "snack", "pitha", "sweet", "tea stall")),
    ("electronics", ("mobile", "phone", "electronic", "gadget", "computer", "charger")),
    ("books", ("book", "stationer", "library", "paper")),
    ("clothing", ("fashion", "garment", "tailor", "boutique", "cloth", "trims", "textile", "knit")),
]
INVOICE_KIND = {"customer": "receivable", "supplier": "payable"}


def pick_book(*text: str | None) -> str:
    """Which book suits this business, from its name, sector and the owner's own description."""
    blob = " ".join(t for t in text if t).lower()
    for name, words in KEYWORDS:
        if any(w in blob for w in words):
            return name
    return DEFAULT_BOOK


def book_for(business) -> str:
    about = (business.prefs or {}).get("about") if isinstance(business.prefs, dict) else None
    return pick_book(business.name, business.sector, about)


def _anchors(db: Session, business_id: int, kind: str) -> list[tuple[str, str, str, str]]:
    """Names this business has already invoiced: they go on the list first, with real figures behind them."""
    seen: dict[str, str] = {}
    for i in db.scalars(select(Invoice).where(Invoice.business_id == business_id,
                                              Invoice.kind == INVOICE_KIND[kind]).order_by(Invoice.issue_date.desc())):
        seen.setdefault(normalize(i.counterparty), i.counterparty.strip())
    return [(n, "", "", "") for n in seen.values()]


def seed_parties(db: Session, business_id: int, kind: str, book: str, target: int = TARGET) -> list[Party]:
    """Top this business up to ``target`` named parties of one kind. Existing names are never duplicated."""
    have = {k for p in db.scalars(select(Party).where(Party.business_id == business_id, Party.kind == kind))
            for k in [normalize(p.name), *(normalize(a) for a in (p.aliases or []))]}
    made: list[Party] = []
    for name, phone, email, note in _anchors(db, business_id, kind) + BOOKS[book][f"{kind}s"]:
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


def seed_stock(db: Session, business_id: int, book: str, today: date, seed: int = 20261020) -> list[Item]:
    """Stock the business can actually sell, with the purchases and sales that explain today's numbers."""
    rnd = random.Random(seed + business_id)
    have = {normalize(i.name) for i in db.scalars(select(Item).where(Item.business_id == business_id))}
    made: list[Item] = []
    for name, unit, price, daily in BOOKS[book]["stock"]:
        if normalize(name) in have:
            continue
        # Opening is the stock on the shelf HISTORY_DAYS ago; the movements below carry it to today.
        item = Item(business_id=business_id, name=name, aliases=[], unit=unit,
                    opening_qty=float(round(daily * 9)), reorder_level=float(round(daily * 5)), cost_price=price)
        db.add(item)
        db.flush()
        for back in range(HISTORY_DAYS, 0, -1):
            when = datetime.combine(today - timedelta(days=back), datetime.min.time()) + timedelta(hours=18)
            sold = max(0, round(rnd.gauss(daily, daily * 0.35)))
            if sold:
                db.add(StockMovement(item_id=item.id, qty_change=-float(sold), reason="sale", created_at=when))
            if back % 7 == 0:  # a restock about once a week, a little more than the week's sales
                db.add(StockMovement(item_id=item.id, qty_change=float(round(daily * 7.4)), reason="purchase",
                                     created_at=when - timedelta(hours=6)))
        made.append(item)
    db.flush()
    return made


def drop_unused_parties(db: Session, business_id: int) -> int:
    """Remove seeded names that never got any activity, so a business can be re-stocked with the right book.

    A party with an invoice behind it, or one the owner linked by hand, is left exactly where it is.
    """
    linked = {r.party_id for r in db.scalars(select(PartyLink).join(Party, Party.id == PartyLink.party_id)
                                             .where(Party.business_id == business_id))}
    names: dict[str, set[str]] = {}
    for i in db.scalars(select(Invoice).where(Invoice.business_id == business_id)):
        names.setdefault("customer" if i.kind == "receivable" else "supplier", set()).add(normalize(i.counterparty))
    gone = 0
    for p in db.scalars(select(Party).where(Party.business_id == business_id)):
        keys = {normalize(p.name), *(normalize(a) for a in (p.aliases or []))}
        if p.id in linked or keys & names.get(p.kind, set()):
            continue
        db.delete(p)
        gone += 1
    db.flush()
    return gone




# Typical invoice size per book, so a kitchen bills in hundreds and an electronics shop in thousands.
INVOICE_RANGE = {"food": (900, 9000), "electronics": (4000, 48000), "books": (1200, 16000), "clothing": (6000, 95000)}
INVOICES_PER_PARTY = (2, 5)


def seed_invoices(db: Session, business_id: int, book: str, today: date, seed: int = 20261020) -> list[Invoice]:
    """Give every named party a short trading history: some paid, some still open, some already late.

    Amounts and dates are invented, but the figures the app shows are not: balances, what is overdue and how
    often someone comes are all counted back out of these rows, the same way they are for real records.
    """
    rnd = random.Random(seed + business_id * 31)
    low, high = INVOICE_RANGE.get(book, INVOICE_RANGE[DEFAULT_BOOK])
    used = {i.invoice_no for i in db.scalars(select(Invoice).where(Invoice.business_id == business_id))}
    made: list[Invoice] = []
    for party in db.scalars(select(Party).where(Party.business_id == business_id).order_by(Party.id)):
        if any(normalize(i.counterparty) == normalize(party.name) for i in invoices_of_kind(db, business_id, party.kind)):
            continue                                        # already has records of its own; leave them alone
        prefix = "INV" if party.kind == "customer" else "BILL"
        for n in range(rnd.randint(*INVOICES_PER_PARTY)):
            issued = today - timedelta(days=rnd.randint(5, 110))
            due = issued + timedelta(days=rnd.choice([7, 15, 30]))
            amount = float(round(rnd.uniform(low, high), -1))
            roll = rnd.random()
            if roll < 0.55:                                  # settled
                paid, paid_on, status = amount, due - timedelta(days=rnd.randint(0, 6)), "paid"
            elif roll < 0.75:                                # part payment against it
                paid, paid_on, status = float(round(amount * rnd.uniform(0.2, 0.7), -1)), issued + timedelta(days=5), "partial"
            else:                                            # still to be settled
                paid, paid_on, status = 0.0, None, "open"
            if paid_on and paid_on > today:
                paid_on = today
            no = f"{prefix}-{business_id:02d}{party.id:03d}{n + 1}"
            if no in used:
                continue
            used.add(no)
            inv = Invoice(business_id=business_id, kind=INVOICE_KIND[party.kind], invoice_no=no,
                          counterparty=party.name, counterparty_phone=party.phone, amount=amount, amount_paid=paid,
                          issue_date=issued, due_date=due, paid_date=paid_on, status=status,
                          notes=party.note or "", source="demo")
            db.add(inv)
            db.flush()
            db.add(PartyLink(invoice_id=inv.id, party_id=party.id, locked=False))
            made.append(inv)
    db.flush()
    return made


def invoices_of_kind(db: Session, business_id: int, kind: str) -> list[Invoice]:
    return list(db.scalars(select(Invoice).where(Invoice.business_id == business_id,
                                                 Invoice.kind == INVOICE_KIND[kind])))

def seed_all(db: Session, business_id: int, book: str, today: date, target: int = TARGET) -> dict[str, int]:
    out = {kind: len(seed_parties(db, business_id, kind, book, target)) for kind in ("customer", "supplier")}
    out["stock"] = len(seed_stock(db, business_id, book, today))
    out["invoices"] = len(seed_invoices(db, business_id, book, today))
    out["barcodes"] = len(seed_barcodes(db, business_id))
    out["book"] = book
    return out


def _ean13(digits12: str) -> str:
    """Append the EAN-13 check digit, so demo codes are the shape a real scanner emits."""
    odd = sum(int(d) for d in digits12[0::2])
    even = sum(int(d) for d in digits12[1::2])
    return digits12 + str((10 - (odd + even * 3) % 10) % 10)


def seed_barcodes(db: Session, business_id: int, seed: int = 20261020) -> list[ItemBarcode]:
    """Put a code on every item that has none, so scanning can be shown without labelling real stock first.

    The prefix 200-299 is the range reserved for in-store use, which is exactly what these are.
    """
    rnd = random.Random(seed + business_id * 7)
    have = {b.item_id for b in db.scalars(select(ItemBarcode).where(ItemBarcode.business_id == business_id))}
    used = {b.code for b in db.scalars(select(ItemBarcode).where(ItemBarcode.business_id == business_id))}
    made: list[ItemBarcode] = []
    for it in db.scalars(select(Item).where(Item.business_id == business_id).order_by(Item.id)):
        if it.id in have:
            continue
        for _ in range(20):
            code = _ean13(f"2{business_id:02d}{rnd.randint(0, 999999999):09d}")
            if code not in used:
                break
        else:
            continue
        used.add(code)
        row = ItemBarcode(business_id=business_id, item_id=it.id, code=code)
        db.add(row)
        made.append(row)
    db.flush()
    return made
