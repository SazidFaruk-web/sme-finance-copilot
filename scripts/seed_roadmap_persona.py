"""Eight months of a fictional owner's records, so the goal roadmap has something real to read.

Persona (entirely made up): Rokeya Begum cooks at home in Sylhet and sells biryani, pitha, chicken curry
and snacks through a Facebook page, delivered around the city. She has recorded every day since
March 2026: order payments by bKash and cash, ingredient and gas purchases, delivery riders,
packaging, her house rent, and the money she takes home. Ramadan and the two Eids are her busy
months; the monsoon is quiet.

She is saving for a commercial oven (about 2.5 lakh) and, further out, a place of her own (about
20 lakh) — the two goals that exercise the short and the long roadmap shapes.

Writes to a SEPARATE data folder, so the normal demo database is untouched:

    .venv/Scripts/python scripts/seed_roadmap_persona.py
    set DATA_DIR=data/roadmap-test & .venv/Scripts/python -m sme_copilot.cli serve --port 8011

Login: rokeya-plan / rokeya-demo-2026
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ROADMAP_DATA_DIR", ROOT / "data" / "roadmap-test"))
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("APP_ENV", "demo")
os.environ.setdefault("AS_OF_DATE", "2026-10-20")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # the .env field-encryption key must match the server's

from sqlalchemy import select  # noqa: E402

from sme_copilot import home_layout as hl  # noqa: E402
from sme_copilot.config import get_settings, reset_settings_cache  # noqa: E402
from sme_copilot.db import SessionLocal, init_db, reset_engine  # noqa: E402
from sme_copilot.models import Business, HomePrefs, Invoice, Item, Obligation, Transaction, User  # noqa: E402
from sme_copilot.security.auth import create_user  # noqa: E402

TODAY = date(2026, 10, 20)
START = date(2026, 3, 1)          # first recorded day
OPENING = 18_000.0
USER, PASSWORD = "rokeya-plan", os.environ.get("DEMO_ROKEYA_PLAN_PASSWORD", "rokeya-demo-2026")
rnd = random.Random(20260901)

# Month-by-month trade, as her records show it. 1.0 is an ordinary month.
#   Ramadan 2026 ran through most of March; Eid-ul-Fitr fell in late March, Eid-ul-Azha in late May.
#   Sylhet's heaviest rain is June to August, when deliveries drop.
SEASON = {1: 0.95, 2: 1.05, 3: 1.55, 4: 1.20, 5: 1.35, 6: 0.78, 7: 0.70, 8: 0.80,
          9: 1.00, 10: 1.15, 11: 1.05, 12: 1.10}
BASE_ORDERS_PER_DAY = 4.16        # an ordinary day
AVERAGE_ORDER = 640.0             # what an order is worth on average, used to size ingredient buying

MENU = [("Biryani tray", 1200.0, 760.0), ("Chicken curry (half kg)", 520.0, 330.0),
        ("Pitha box (12 pcs)", 400.0, 230.0), ("Snack box", 260.0, 150.0),
        ("Khichuri pot", 680.0, 420.0)]

CUSTOMERS = ["Nusrat Jahan", "Shahin Ahmed", "Farhana Akter", "Rezaul Karim", "Tanzila Rahman",
             "Mizanur Rahman", "Sumaiya Islam", "Abdul Mannan"]
SUPPLIERS = ["Zindabazar Grocery", "Ambarkhana Poultry", "Kazi Rice Agency", "Lamabazar Packaging"]


def month_scale(d: date) -> float:
    return SEASON[d.month]


def seed() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reset_settings_cache()
    reset_engine()
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == USER)):
            print(f"{USER} already exists in {DATA_DIR}. Delete the folder to reseed.")
            return

        business = Business(
            name="Rokeya's Kitchen", sector="restaurant_food", district="Sylhet", owner_name="Rokeya Begum",
            established_on=date(2026, 2, 15), has_bank_account=False, women_led=True,
            opening_cash_balance=OPENING, opening_balance_date=START - timedelta(days=1),
            low_balance_threshold=15_000,
            prefs={"about": "Homemade food sold through Facebook: biryani, pitha, chicken curry and snacks, "
                            "delivered in Sylhet city", "mode": "simple", "language": "en"})
        db.add(business)
        db.flush()
        user = create_user(db, business_id=business.id, username=USER, password=PASSWORD, role="owner",
                           full_name="Rokeya Begum")
        # Setup is already done for this persona: the app must open straight into the app, not the wizard.
        db.add(HomePrefs(user_id=user.id, business_id=business.id, **hl.normalize_prefs(
            business_type=hl.type_key("restaurant_food", "homemade food sold through Facebook"),
            mode="simplified", widgets=hl.SIMPLIFIED, nav=None, style="general")))

        for name, _price, cost in MENU:
            db.add(Item(business_id=business.id, name=name, unit="order", cost_price=cost))

        db.add(Obligation(business_id=business.id, name="House and kitchen rent", category="rent",
                          amount=9000, frequency="monthly", day_of_month=5,
                          next_due=date(2026, 11, 5), active=True, source="user"))
        db.add(Obligation(business_id=business.id, name="Gas cylinder subscription", category="utilities",
                          amount=2800, frequency="monthly", day_of_month=12,
                          next_due=date(2026, 11, 12), active=True, source="user"))

        rows: list[Transaction] = []
        day = START
        while day <= TODAY:
            scale = month_scale(day)
            weekend_lift = 1.35 if day.weekday() in (3, 4) else 1.0   # Thursday and Friday are her busiest
            orders = max(0, int(round(rnd.gauss(BASE_ORDERS_PER_DAY * scale * weekend_lift, 1.6))))
            for _ in range(orders):
                item, price, cost = MENU[rnd.randrange(len(MENU))]
                amount = round(price * rnd.uniform(0.85, 1.25), 2)
                rows.append(Transaction(
                    business_id=business.id, txn_date=day, amount=amount, direction="in", category="sales",
                    counterparty=CUSTOMERS[rnd.randrange(len(CUSTOMERS))], description=f"{item} order",
                    channel="bkash" if rnd.random() < 0.62 else "cash", item=item, quantity=1,
                    source="manual", categorized_by="user"))

            # Ingredients bought most days, roughly in step with what sold.
            if orders:
                spend = round(orders * AVERAGE_ORDER * rnd.uniform(0.40, 0.48), 2)
                rows.append(Transaction(
                    business_id=business.id, txn_date=day, amount=spend, direction="out",
                    category="stock_purchase", counterparty=SUPPLIERS[rnd.randrange(len(SUPPLIERS))],
                    description="Rice, chicken, oil and spices", channel="cash", source="manual",
                    categorized_by="user"))
            if orders and rnd.random() < 0.8:
                rows.append(Transaction(
                    business_id=business.id, txn_date=day, amount=round(orders * rnd.uniform(28, 42), 2),
                    direction="out", category="delivery", counterparty="Delivery rider",
                    description="Rider payments for the day", channel="bkash", source="manual",
                    categorized_by="user"))

            if day.day == 5:
                rows.append(Transaction(business_id=business.id, txn_date=day, amount=9000, direction="out",
                                        category="rent", counterparty="Landlord", description="House and kitchen rent",
                                        channel="cash", source="manual", categorized_by="user"))
            if day.day == 12:
                rows.append(Transaction(business_id=business.id, txn_date=day, amount=2800, direction="out",
                                        category="utilities", counterparty="Gas supplier",
                                        description="Gas cylinders", channel="cash", source="manual",
                                        categorized_by="user"))
            if day.day == 18:
                rows.append(Transaction(business_id=business.id, txn_date=day,
                                        amount=round(rnd.uniform(1900, 3100), 2), direction="out",
                                        category="packaging", counterparty="Lamabazar Packaging",
                                        description="Boxes, foil and bags", channel="cash", source="manual",
                                        categorized_by="user"))
            if day.day == 22:
                rows.append(Transaction(business_id=business.id, txn_date=day,
                                        amount=round(rnd.uniform(900, 1500), 2), direction="out",
                                        category="marketing", counterparty="Facebook",
                                        description="Boosted the page", channel="bkash", source="manual",
                                        categorized_by="user"))
            if day.day == 28:
                rows.append(Transaction(business_id=business.id, txn_date=day, amount=13500, direction="out",
                                        category="owner_drawings", counterparty="",
                                        description="Money taken home for the family", channel="cash",
                                        source="manual", categorized_by="user"))
            day += timedelta(days=1)
        db.add_all(rows)

        # Two office caterers who pay on account, so the planner has receivables to weigh.
        db.add(Invoice(business_id=business.id, kind="receivable", invoice_no="RK-2026-114",
                       counterparty="Sylhet IT Park canteen", amount=18500, amount_paid=0,
                       issue_date=date(2026, 10, 2), due_date=date(2026, 10, 30), status="open",
                       notes="Weekly lunch trays, September", source="manual"))
        db.add(Invoice(business_id=business.id, kind="receivable", invoice_no="RK-2026-117",
                       counterparty="Shahjalal Coaching Centre", amount=7200, amount_paid=3000,
                       issue_date=date(2026, 10, 9), due_date=date(2026, 11, 8), status="partial",
                       notes="Snack boxes for exam week", source="manual"))
        db.add(Invoice(business_id=business.id, kind="payable", invoice_no="ZG-7781",
                       counterparty="Zindabazar Grocery", amount=11400, amount_paid=0,
                       issue_date=date(2026, 10, 12), due_date=date(2026, 10, 27), status="open",
                       notes="Rice and oil on credit", source="manual"))
        db.commit()

        money_in = sum(r.amount for r in rows if r.direction == "in")
        money_out = sum(r.amount for r in rows if r.direction == "out")
        months = 8
        print(f"Seeded {len(rows)} records for {business.name} in {DATA_DIR}")
        print(f"  {START} to {TODAY} · money in ~{money_in:,.0f} · money out ~{money_out:,.0f}")
        print(f"  average month: in ~{money_in / months:,.0f}, out ~{money_out / months:,.0f}, "
              f"left over ~{(money_in - money_out) / months:,.0f}")
        print(f"  cash now ~{OPENING + money_in - money_out:,.0f}")
        print(f"\nLogin: {USER} / {PASSWORD}")
        print(f"Run:   set DATA_DIR={DATA_DIR.relative_to(ROOT)} & "
              f".venv/Scripts/python -m sme_copilot.cli serve --port 8011")


if __name__ == "__main__":
    seed()
    print(f"\nsettings data dir: {get_settings().data_dir}")
