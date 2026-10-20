"""Four fictional test owners for the demo login screen (owner decision 2026-10-19).

Each one is a separate business with its own history, imported through the same code path as an owner's upload:

* Tanvir Hossain, mobile phone accessories, Chattogram: about 3 months of records, credit customers, a supplier bill.
* Shirin Akter, bookshop near Rajshahi University: 1 month, a semester rush then a slow month, publisher bills.
* Rokeya Begum, homemade food via Facebook, Sylhet: 15 days of bKash and cash orders.
* Rafi Ahmed, new clothes seller, Khulna: a brand-new account that goes through setup and the tour himself.

All names, phone numbers and amounts are made up. Passwords come from DEMO_<NAME>_PASSWORD (see .env.example).
"""
from __future__ import annotations

import csv
import io
import os
import random
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot import home_layout as hl
from sme_copilot.market import catalog, watch
from sme_copilot.models import Business, HomePrefs, MarketWatch, Obligation, SandboxAccount, User
from sme_copilot.demo import trade_book
from sme_copilot.security.auth import create_user
from sme_copilot.tools.ingestion import import_file

PERSONAS: dict[str, dict[str, Any]] = {
    "tanvir": {"full_name": "Tanvir Hossain", "business": "Tanvir Mobile Corner", "district": "Chattogram", "days": 92,
               "opening": 85000, "established": date(2021, 2, 1), "type": "retail",
               "about": "Mobile phone accessories shop in Reazuddin Bazar: covers, chargers, earphones, screen protectors, power banks",
               "summary": "mobile phone accessories shop", "licence": True, "tin": True, "bank": True},
    "shirin": {"full_name": "Shirin Akter", "business": "Boighor Book Corner", "district": "Rajshahi", "days": 30,
               "opening": 40000, "established": date(2019, 7, 1), "type": "retail",
               "about": "Bookshop near Rajshahi University selling textbooks, guide books, novels and stationery",
               "summary": "bookshop near Rajshahi University", "licence": True, "tin": False, "bank": True},
    "rokeya": {"full_name": "Rokeya Begum", "business": "Rokeya's Kitchen", "district": "Sylhet", "days": 15,
               "opening": 12000, "established": None, "type": "restaurant_food",
               "about": "Homemade food sold through Facebook: biryani, pitha, chicken curry and snacks, delivered in Sylhet city",
               "summary": "homemade food sold through Facebook", "licence": False, "tin": False, "bank": False},
    "rafi": {"full_name": "Rafi Ahmed", "business": "Rafi Fashion", "district": "Khulna", "days": 0, "opening": 0,
             "established": None, "type": None, "about": "", "summary": "", "licence": False, "tin": False, "bank": False},
}


def password(username: str) -> str:
    return os.environ.get(f"DEMO_{username.upper()}_PASSWORD", f"{username}-demo-2026")


def demo_logins() -> list[dict[str, str]]:
    """What the login screen offers in demo deployments."""
    return [{"username": u, "password": password(u), "role": "owner", "name": p["full_name"], "business": p["business"],
             "note": "new account" if not p["days"] else f"{p['days']} days of records"} for u, p in PERSONAS.items()]


# ----------------------------------------------------------------------------- histories (deterministic)
def _d(x: date) -> str:
    return x.strftime("%d/%m/%Y")


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _tanvir(start: date, today: date, rnd: random.Random):
    sales, exp, wallet, inv = [], [], [], []
    items = ["Phone covers", "Chargers and cables", "Earphones", "Screen protectors", "Power bank", "Bluetooth speaker"]
    day = start
    while day <= today:
        boost = 1.25 if day.month == today.month else 1.0
        for _ in range(rnd.randint(2, 3)):
            sales.append([_d(day), f"Counter sales ({rnd.choice(items)})", round(rnd.uniform(1800, 5200) * boost, -1), "income", "Walk-in customers"])
        if day.day == 5:
            exp.append([_d(day), "Shop rent Reazuddin Bazar", 18000, "expense", "Market committee"])
        if day.day == 1:
            exp.append([_d(day), "Salary - helper Sumon", 9000, "expense", "Sumon"])
        if day.day == 12:
            exp.append([_d(day), "Electricity bill (PDB)", rnd.choice([2350, 2600, 2900]), "expense", "BPDB"])
            exp.append([_d(day), "Internet bill", 1000, "expense", "Link3"])
        if (day - start).days % 10 == 3:
            exp.append([_d(day), "Stock purchase - covers, chargers, earphones", round(rnd.uniform(38000, 62000), -2), "expense", "Dhaka Gadget Wholesale"])
        if (day - start).days % 6 == 0:
            exp.append([_d(day), "Tea, snacks and transport", rnd.randint(250, 700), "expense", ""])
        if rnd.random() < 0.55:
            wallet.append([f"{day.isoformat()} 1{rnd.randint(0, 9)}:{rnd.randint(10, 59)}:00", f"TRX{rnd.randint(100000, 999999)}",
                           "Received Money", f"017{rnd.randint(10000000, 99999999)}", float(rnd.randint(350, 2600)), 0, 0, "Success"])
        day += timedelta(days=1)
    for n, (cust, amt, issued, due, paid) in enumerate([
            ("Rahman Mobile Servicing", 24500, today - timedelta(days=70), today - timedelta(days=40), today - timedelta(days=35)),
            ("Rahman Mobile Servicing", 31800, today - timedelta(days=38), today - timedelta(days=8), None),
            ("Agrabad Phone Point", 18600, today - timedelta(days=50), today - timedelta(days=20), None),
            ("Agrabad Phone Point", 12200, today - timedelta(days=12), today + timedelta(days=18), None)], 1):
        inv.append([f"TMC-{n:03d}", cust, amt, _d(issued), _d(due), _d(paid) if paid else "", "", "Accessories on credit"])
    bills = [["DGW-881", "Dhaka Gadget Wholesale", 65000, _d(today - timedelta(days=23)), _d(today + timedelta(days=7)), "", "payable"]]
    obligations = [("Shop rent", "rent", 18000, 5), ("Electricity bill", "utilities", 2600, 12)]
    return sales, exp, wallet, inv, bills, obligations


def _shirin(start: date, today: date, rnd: random.Random):
    sales, exp = [], []
    day = start
    while day <= today:
        rush = (day - start).days < 10  # semester start, then it slows down
        for _ in range(rnd.randint(2, 4) if rush else rnd.randint(1, 2)):
            sales.append([_d(day), rnd.choice(["Textbooks (HSC/Honours)", "Guide books", "Novels", "Stationery"]),
                          round(rnd.uniform(1500, 6000) if rush else rnd.uniform(400, 1800), -1), "income", "Students"])
        if day.day == 1:
            exp.append([_d(day), "Shop rent", 12000, "expense", "Landlord"])
        if day.day == 10:
            exp.append([_d(day), "Electricity bill", 1450, "expense", "NESCO"])
        if day.day == 7:
            exp.append([_d(day), "Salary - shop assistant", 7000, "expense", "Karim"])
        if (day - start).days in (2, 16):
            exp.append([_d(day), "Books from Banglabazar publishers (cash part)", 35000 if (day - start).days == 2 else 28000, "expense", "Banglabazar"])
        if (day - start).days % 5 == 0:
            exp.append([_d(day), "Courier and transport", rnd.randint(300, 900), "expense", ""])
        day += timedelta(days=1)
    inv = [["BBC-001", "Udvash Coaching Centre", 22000, _d(start + timedelta(days=4)), _d(start + timedelta(days=19)), "", "", "Guide books on credit"],
           ["BBC-002", "Mitu (student)", 1800, _d(start + timedelta(days=9)), _d(start + timedelta(days=16)), "", "", "Baki"]]
    bills = [["AP-2219", "Anupam Prokashoni", 48000, _d(start + timedelta(days=2)), _d(today + timedelta(days=4)), "", "payable"],
             ["PP-118", "Panjeree Publications", 26500, _d(start + timedelta(days=16)), _d(today + timedelta(days=16)), "", "payable"]]
    return sales, exp, [], inv, bills, [("Shop rent", "rent", 12000, 1)]


def _rokeya(start: date, today: date, rnd: random.Random):
    sales, exp, wallet = [], [], []
    day = start
    while day <= today:
        for _ in range(rnd.randint(1, 3)):
            item = rnd.choice(["Chicken biryani order", "Pitha box order", "Chicken curry and rice order", "Snacks platter order"])
            amt = round(rnd.uniform(700, 3200), -1)
            if rnd.random() < 0.7:
                wallet.append([f"{day.isoformat()} 2{rnd.randint(0, 2)}:{rnd.randint(10, 59)}:00", f"BK{rnd.randint(100000, 999999)}",
                               "Received Money", f"019{rnd.randint(10000000, 99999999)}", float(amt), 0, 0, "Success"])
            else:
                sales.append([_d(day), item + " (cash on delivery)", amt, "income", "Facebook customer"])
        if rnd.random() < 0.6:
            exp.append([_d(day), rnd.choice(["Chicken and meat", "Rice, oil and spices", "Vegetables", "Flour and sugar for pitha"]),
                        round(rnd.uniform(900, 3500), -1), "expense", "Zindabazar market"])
        if (day - start).days % 7 == 0:
            exp.append([_d(day), "Gas cylinder (12 kg)", 1450, "expense", ""])
        if rnd.random() < 0.5:
            exp.append([_d(day), "Delivery boy (Pathao)", rnd.choice([80, 120, 150]), "expense", "Pathao"])
        if (day - start).days == 3:
            exp.append([_d(day), "Facebook page boost", 1500, "expense", "Meta"])
            exp.append([_d(day), "Food boxes and packaging", 2200, "expense", ""])
        day += timedelta(days=1)
    inv = [["RK-01", "Office lunch - Sylhet IT Park", 9600, _d(today - timedelta(days=9)), _d(today - timedelta(days=2)), "", "", "Lunch boxes, to pay at month end"]]
    return sales, exp, wallet, inv, [], []


MAKERS = {"tanvir": _tanvir, "shirin": _shirin, "rokeya": _rokeya}
TXN_HEADER = ["Date", "Description", "Amount", "Type", "Party"]


def _next_due(today: date, day: int) -> date:
    due = today.replace(day=day)
    return due if due >= today - timedelta(days=10) else (due.replace(month=due.month % 12 + 1, year=due.year + (due.month == 12)))


def load_personas(session: Session, as_of: date, seed: int = 20261019) -> dict[str, Any]:
    """Add missing demo owners without resetting existing accounts, passwords or records."""
    rnd = random.Random(seed)
    report: dict[str, Any] = {}
    for username, p in PERSONAS.items():
        if session.scalar(select(User.id).where(User.username == username)) is not None:
            report[username] = {"existing": True}
            continue
        created = datetime.combine(as_of - timedelta(days=p["days"]), datetime.min.time()) + timedelta(hours=10)
        b = Business(name=p["business"], sector=p["summary"] or "trading", district=p["district"], owner_name=p["full_name"],
                     established_on=p["established"], has_trade_license=p["licence"], has_tin=p["tin"], has_bank_account=p["bank"],
                     opening_cash_balance=p["opening"], opening_balance_date=as_of - timedelta(days=p["days"] + 1),
                     prefs={"number_style": "lakh", "language": "en", **({"about": p["about"]} if p["about"] else {})}, created_at=created)
        session.add(b)
        session.flush()
        user = create_user(session, b.id, username, password(username), "owner", p["full_name"])
        user.created_at = created
        session.add(SandboxAccount(business_id=b.id, name="Sandbox Operating Account", account_no=f"SBX-{b.id:010d}", balance=0))
        session.flush()
        rows: dict[str, int] = {}
        if username in MAKERS:  # Rafi has just opened the app: no history, no setup yet
            sales, exp, wallet, inv, bills, obligations = MAKERS[username](as_of - timedelta(days=p["days"]), as_of, rnd)
            files = [("sales.csv", "sales", _csv(TXN_HEADER, sales)), ("expenses.csv", "expenses", _csv(TXN_HEADER, exp)),
                     ("bkash.csv", "wallet", _csv(["Date", "Trx ID", "Transaction Type", "Counterparty", "Amount", "Fee", "Balance", "Status"], wallet)),
                     ("customer_credit.csv", "invoices", _csv(["Invoice No", "Customer", "Amount", "Invoice Date", "Due Date", "Paid Date", "Phone", "Notes"], inv)),
                     ("supplier_bills.csv", "invoices", _csv(["Invoice No", "Supplier", "Amount", "Invoice Date", "Due Date", "Paid Date", "Type"], bills))]
            for name, doc, content in files:
                if content.count(b"\n") > 1:
                    rows[name] = import_file(session, b.id, content, name, doc_type=doc, actor=username).imported
            for name, cat, amount, day in obligations:
                session.add(Obligation(business_id=b.id, name=name, category=cat, amount=amount, day_of_month=day,
                                       next_due=_next_due(as_of, day), source="user"))
            bt = hl.type_key(p["type"], p["summary"])
            session.add(HomePrefs(user_id=user.id, business_id=b.id, **hl.normalize_prefs(
                business_type=bt, mode="simplified", widgets=hl.SIMPLIFIED, nav=None, style="general")))
            items = watch.rule_pick(p["business"], p["type"], p["about"])
            session.add(MarketWatch(user_id=user.id, business_id=b.id, items=items, source="rules", reason=p["summary"]))
            if catalog.goods_without_prices(p["business"], p["about"]):
                rows["prices"] = "running costs (no public prices for these goods)"
        session.flush()
        rows["trade"] = trade_book.seed_all(session, b.id, trade_book.book_for(b), as_of)  # names and stock to start from
        report[username] = {"business": p["business"], "district": p["district"], "imported": rows}
    session.commit()
    return report
