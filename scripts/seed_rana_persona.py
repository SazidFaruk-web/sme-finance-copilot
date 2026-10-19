"""Two months of a fictional owner's life, for testing the app end to end.

Persona (all made up): Md. Rana Hossain runs "Rana Electric & Hardware" on Nawabpur Road, Dhaka (Dhaka South).
He sells drill machines, grinders, fans, LED bulbs, wire coils, MCBs, switch boards and small tools to walk-in
customers and, on credit, to electricians and building contractors. He joined the app on 20 Aug 2026 and by
19 Oct 2026 has: daily typed entries, weekly khata uploads, bank and bKash statements, customer invoices and
supplier bills, stock items, AI Assistant chats (growth advice, a bank loan, letters), guided tasks, appointments,
SMS reminders, sandbox payments, loan-readiness reports and a hash-chained audit log.

Writes to a SEPARATE data folder so the normal demo database is untouched:

    .venv/Scripts/python scripts/seed_rana_persona.py            # -> data/rana-test/copilot.db
    set DATA_DIR=data/rana-test & .venv/Scripts/python -m sme_copilot.cli serve --port 8010

Login: rana / rana-demo-2026
"""
from __future__ import annotations

import csv
import io
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RANA_DATA_DIR", ROOT / "data" / "rana-test"))
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("APP_ENV", "demo")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # .env (encryption key) must match the server's

from sqlalchemy import select, update  # noqa: E402

from sme_copilot import home_layout as hl  # noqa: E402
from sme_copilot.config import get_settings  # noqa: E402
from sme_copilot.db import SessionLocal, init_db, reset_engine  # noqa: E402
from sme_copilot.market import watch  # noqa: E402
from sme_copilot.models import (  # noqa: E402
    Alert, AuditEvent, Business, ChatMessage, Conversation, Draft, HomePrefs, ImportBatch, Invoice, InvoiceLine,
    InvoicePayment, Item, MarketWatch, Obligation, PendingAction, RecurringInvoice, Reminder, Report, SandboxAccount,
    SandboxTransfer, StockMovement, Transaction)
from sme_copilot.pilot.definitions import questions  # noqa: E402
from sme_copilot.pilot.models import GuidedCase, NotificationPreference  # noqa: E402
from sme_copilot.pilot import service as pilot  # noqa: E402
from sme_copilot.security.audit import GENESIS, _event_dict, _jsonable, compute_hash  # noqa: E402
from sme_copilot.security.auth import create_user  # noqa: E402
from sme_copilot.security.pii import mask_obj  # noqa: E402
from sme_copilot.tools.ingestion import import_file  # noqa: E402

START = date(2026, 8, 20)
TODAY = date(2026, 10, 19)
OPENING = 120_000.0
USER = "rana"
PASSWORD = os.environ.get("DEMO_RANA_PASSWORD", "rana-demo-2026")
IP = "192.168.0.105"
rnd = random.Random(20260820)
NOW = datetime.now().astimezone().astimezone(__import__('datetime').timezone.utc).replace(tzinfo=None)


def at(d: date, hm: str) -> datetime:
    """Dhaka local time -> naive UTC (how the app stores timestamps)."""
    h, m = map(int, hm.split(":"))
    return datetime(d.year, d.month, d.day, h, m) - timedelta(hours=6)


def dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def tk(v: float) -> str:
    """Lakh-style taka, as the app writes it."""
    v = round(v)
    s = str(abs(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if v < 0 else "") + "৳" + s


# ----------------------------------------------------------------------------- catalogue
# key: (name, unit, cost, price, opening qty, reorder level, daily chance, (min,max) per sale day, aliases)
ITEMS = {
    "drill":   ("Drill machine 13mm (Bosch GSB 550)", "pcs", 5200, 6500, 8, 3, .22, (1, 1), ["drill", "drill machine"]),
    "grinder": ("Angle grinder 4 inch", "pcs", 3100, 3900, 10, 3, .25, (1, 2), ["grinder", "angle grinder"]),
    "bits":    ("Hammer drill bit set", "set", 450, 650, 30, 10, .35, (1, 3), ["drill bit", "bit set"]),
    "fan":     ("Ceiling fan 56 inch", "pcs", 2900, 3500, 25, 8, .60, (1, 2), ["ceiling fan", "fan"]),
    "pfan":    ("Pedestal fan 18 inch", "pcs", 2400, 2950, 12, 4, .30, (1, 2), ["pedestal fan", "stand fan"]),
    "led12":   ("LED bulb 12W", "pcs", 120, 170, 300, 100, .90, (5, 22), ["12w bulb", "led bulb", "bulb"]),
    "led18":   ("LED bulb 18W", "pcs", 165, 230, 200, 60, .70, (3, 12), ["18w bulb"]),
    "tube":    ("LED tube light 20W", "pcs", 260, 350, 120, 40, .60, (2, 8), ["tube light", "tube"]),
    "w15":     ("Electric wire 1.5 rm (90m coil)", "coil", 2350, 2750, 70, 12, .50, (1, 3), ["1.5 rm wire", "1.5 wire", "wire 1.5"]),
    "w25":     ("Electric wire 2.5 rm (90m coil)", "coil", 3700, 4300, 40, 8, .40, (1, 2), ["2.5 rm wire", "2.5 wire", "wire 2.5"]),
    "mcb":     ("MCB circuit breaker 32A", "pcs", 380, 520, 80, 20, .50, (2, 6), ["mcb", "circuit breaker", "breaker"]),
    "switch":  ("Switch socket board", "pcs", 85, 130, 400, 120, .80, (8, 30), ["switch board", "switch", "socket"]),
    "ext":     ("Extension board 4-plug", "pcs", 280, 380, 50, 15, .50, (1, 4), ["extension board", "multiplug"]),
    "screw":   ("Screwdriver set", "set", 220, 320, 40, 10, .30, (1, 2), ["screwdriver"]),
    "tape":    ("PVC insulation tape", "roll", 25, 40, 500, 150, .80, (8, 30), ["tape", "insulation tape"]),
    "elight":  ("Rechargeable emergency light", "pcs", 650, 950, 0, 6, .55, (1, 3), ["emergency light", "charger light"]),
    "heater":  ("Room heater 2000W", "pcs", 1650, 2200, 0, 4, .25, (1, 1), ["room heater", "heater"]),
    "fairy":   ("LED fairy light string 10m", "pcs", 180, 280, 0, 30, .55, (3, 12), ["fairy light", "string light", "decoration light"]),
    "strip":   ("LED strip light 5m", "roll", 420, 600, 0, 10, .35, (1, 4), ["led strip", "strip light"]),
}
SHORT = {"drill": "drill machine", "grinder": "angle grinder", "bits": "drill bit set", "fan": "ceiling fan",
         "pfan": "pedestal fan", "led12": "12W LED bulb", "led18": "18W LED bulb", "tube": "tube light",
         "w15": "coil 1.5 rm wire", "w25": "coil 2.5 rm wire", "mcb": "MCB", "switch": "switch board",
         "ext": "extension board", "screw": "screwdriver set", "tape": "tape roll", "elight": "emergency light",
         "heater": "room heater", "fairy": "fairy light", "strip": "LED strip"}

ITEM_SUPPLIER = {"drill": "tools", "grinder": "tools", "bits": "tools", "screw": "tools", "fan": "fan", "pfan": "fan",
                 "led12": "light", "led18": "light", "tube": "light", "switch": "light", "ext": "light",
                 "w15": "cable", "w25": "cable", "mcb": "cable", "tape": "cable", "elight": "market", "heater": "tools", "fairy": "light", "strip": "light"}
STOP_RESTOCK = {"fan": date(2026, 9, 21), "pfan": date(2026, 8, 25), "mcb": date(2026, 9, 20), "tape": date(2026, 10, 10),
                "switch": date(2026, 10, 12), "elight": START, "heater": START, "fairy": START, "strip": START}

SUPPLIERS = {"fan": "Dhaka Fan Agency", "light": "Bright Light Wholesale", "cable": "Rahman Cable Traders",
             "tools": "Chawkbazar Tools Import", "market": "Nawabpur Light Market"}

# (date, supplier, {item: qty}, how) how: bank (cheque on statement) | cash | bill:<no>:<due>[:paid via sandbox on]
PURCHASES = [
    (date(2026, 8, 22), "fan", {"fan": 30, "pfan": 10}, "bill:DFA-2231:2026-09-21"),
    (date(2026, 8, 27), "light", {"led12": 200, "led18": 100, "tube": 60, "switch": 300}, "bank"),
    (date(2026, 9, 5), "cable", {"w15": 30, "w25": 15, "mcb": 40, "tape": 400}, "bill:RCT-0917:2026-10-30"),
    (date(2026, 9, 12), "tools", {"drill": 6, "grinder": 8, "bits": 30, "screw": 20}, "bank"),
    (date(2026, 9, 18), "market", {"elight": 20}, "cash"),
    (date(2026, 9, 26), "light", {"led12": 200, "switch": 300, "ext": 40}, "bank"),
    (date(2026, 10, 3), "market", {"elight": 30}, "cash"),
    (date(2026, 10, 8), "tools", {"drill": 10, "grinder": 10, "bits": 40, "heater": 15, "screw": 20}, "bank+bill:CTI-3308:2026-11-07:100000"),
    (date(2026, 10, 10), "cable", {"w15": 25, "w25": 15}, "bill:RCT-1002:2026-11-09"),
    (date(2026, 10, 13), "light", {"led12": 250, "led18": 120, "tube": 80}, "bill:BLW-5520:2026-10-28"),
    (date(2026, 10, 15), "light", {"fairy": 400, "strip": 120, "elight": 20}, "bank"),
]

# Customer credit (receivables). (no, customer, phone, issue, due, {item: qty}, payments[(date, amount, channel)], note)
CREDIT = [
    ("RE-0001", "Babul Electric Works", "01715223401", date(2026, 8, 25), date(2026, 9, 8),
     {"w15": 8, "mcb": 20, "switch": 46}, [(date(2026, 9, 14), 20000, "bkash"), (date(2026, 9, 16), None, "cash")],
     "Wiring for a flat in Jatrabari"),
    ("RE-0002", "Al-Amin Construction", "01819447210", date(2026, 8, 28), date(2026, 9, 27),
     {"w25": 6, "w15": 5, "tape": 100, "mcb": 5}, [(date(2026, 9, 26), None, "bank")], "Shyampur site"),
    ("RE-0003", "Green View Apartments", "01911330876", date(2026, 9, 1), date(2026, 9, 10),
     {"led12": 20, "tube": 6, "tape": 25}, [(date(2026, 9, 10), None, "cash")], "Monthly building maintenance"),
    ("RE-0004", "Shahjahan Builders", "01712908844", date(2026, 9, 3), date(2026, 10, 3),
     {"w15": 15, "w25": 10, "mcb": 15, "switch": 120, "ext": 10}, [(date(2026, 10, 1), 60000, "bank")],
     "6-storey building, Keraniganj"),
    ("RE-0005", "Kamal Electrician", "01676112093", date(2026, 9, 8), date(2026, 9, 22),
     {"grinder": 1, "bits": 2, "led18": 7}, [], "Baki - says one bit set was returned"),
    ("RE-0006", "Hotel Sugandha", "01552781190", date(2026, 9, 15), date(2026, 9, 30),
     {"tube": 30, "led18": 20, "ext": 6, "switch": 10}, [(date(2026, 10, 3), None, "cash")], "Hotel rewiring, Lalbagh"),
    ("RE-0007", "Babul Electric Works", "01715223401", date(2026, 9, 20), date(2026, 10, 5),
     {"w15": 6, "mcb": 10, "switch": 45}, [], "Sutrapur shop fit-out"),
    ("RE-0008", "Green View Apartments", "01911330876", date(2026, 10, 1), date(2026, 10, 10),
     {"led12": 20, "tube": 6, "tape": 25}, [(date(2026, 10, 8), None, "bkash")], "Monthly building maintenance"),
    ("RE-0009", "Al-Amin Construction", "01819447210", date(2026, 10, 2), date(2026, 10, 17),
     {"w25": 5, "tape": 80, "tube": 25}, [], "Shyampur site, phase 2"),
    ("RE-0010", "Shahjahan Builders", "01712908844", date(2026, 10, 10), date(2026, 11, 9),
     {"w15": 12, "w25": 8, "switch": 60}, [], "Keraniganj building, floors 4-6"),
    ("RE-0011", "Babul Electric Works", "01715223401", date(2026, 10, 12), date(2026, 10, 27),
     {"drill": 1, "bits": 3, "led12": 40}, [], "Tools and bulbs"),
]

LANDLORD = "Haji Abdul Karim (landlord)"
BANK = "Karnaphuli Commercial Bank PLC"   # fictional
BRANCH = "Nawabpur Road Branch"
LOAN_DAY = date(2026, 10, 6)
LOAN_AMT, LOAN_FEE, EMI = 400_000, 6_000, 18_850


# ----------------------------------------------------------------------------- simulation
class Sim:
    def __init__(self):
        self.stock = {k: v[4] for k, v in ITEMS.items()}
        self.entries = []        # typed quick entries: dict(date, text, amount, dir, cat, channel, item, qty, party, ts)
        self.khata = {}          # week-ending date -> list of rows [date, desc, amount, type, party]
        self.bank = []           # [date, narration, withdrawal, deposit]
        self.bkash = []          # wallet statement rows
        self.moves = []          # (item, qty, reason, date, entry_ref)
        self.bills = []          # payables
        self.invoices = []       # receivables (computed)
        self.cash_purchases = []
        self.bank_refs = {}

    def sell_cap(self, k, q):
        q = min(q, self.stock[k])
        self.stock[k] -= q
        return q

    def week_of(self, d):
        # khata uploaded every Saturday for Sat..Thu (shop closed Friday); last partial week uploaded on Sunday 18 Oct
        end = d + timedelta(days=(5 - d.weekday()) % 7)
        return min(end, date(2026, 10, 18))


sim = Sim()


def auto_restock(d):
    """Reorder what is running low (same-day delivery from Nawabpur/Chawkbazar wholesalers)."""
    orders = {}
    for k, v in ITEMS.items():
        if sim.stock[k] <= v[5] and d < STOP_RESTOCK.get(k, TODAY):
            orders.setdefault(ITEM_SUPPLIER[k], {})[k] = int(round(v[5] * 3.5))
    for sup, items in orders.items():
        ref = f"PUR-{d.isoformat()}-{sup}-auto"
        for k, q in items.items():
            sim.stock[k] += q
            sim.moves.append((k, q, "purchase", d, ref))
        total = purchase_value(items)
        if total < 30000:
            sim.cash_purchases.append((d, SUPPLIERS[sup], items, total, ref))
        else:
            desc = "Stock purchase - " + ", ".join(f"{q} {SHORT[k]}" for k, q in items.items())
            sim.bank.append([d, f"CHQ to {SUPPLIERS[sup]} - {desc}", total, ""])
            sim.bank_refs[(d, total)] = ref


def purchase_value(items):
    return sum(ITEMS[k][2] * q for k, q in items.items())


def run_sim():
    purchases = {p[0]: p for p in PURCHASES}
    credit = {c[3]: [] for c in CREDIT}
    for c in CREDIT:
        credit[c[3]].append(c)
    d = START
    while d <= TODAY:
        open_day = d.weekday() != 4  # closed Friday
        if open_day and d < TODAY:
            auto_restock(d)
        if d in purchases:
            _, sup, items, how = purchases[d]
            for k, q in items.items():
                sim.stock[k] += q
                sim.moves.append((k, q, "purchase", d, f"PUR-{d.isoformat()}-{sup}"))
            total = purchase_value(items)
            name = SUPPLIERS[sup]
            desc = "Stock purchase - " + ", ".join(f"{q} {SHORT[k]}" for k, q in items.items())
            if how == "bank":
                sim.bank.append([d, f"CHQ to {name} - {desc}", total, ""])
                sim.bank_refs[(d, total)] = f"PUR-{d.isoformat()}-{sup}"
            elif how == "cash":
                sim.cash_purchases.append((d, name, items, total, f"PUR-{d.isoformat()}-{sup}"))
            else:
                parts = how.split("+")
                paid_now = 0.0
                for p in parts:
                    if p.startswith("bill:"):
                        _, no, due, *rest = p.split(":")
                        paid_now = float(rest[0]) if rest else 0.0
                        sim.bills.append([no, name, total, d, date.fromisoformat(due), paid_now, desc])
                if paid_now:
                    sim.bank.append([d, f"CHQ to {name} - part payment {sim.bills[-1][0]}", paid_now, ""])
        for c in credit.get(d, []):
            for k, q in c[5].items():
                got = sim.sell_cap(k, q)
                assert got == q, f"not enough {k} for {c[0]} on {d}: have {got} need {q}"
                sim.moves.append((k, -q, "sale", d, c[0]))
        if open_day:
            day_sales(d)
            day_khata(d)
        if d.weekday() == 3 and d < TODAY:  # owner drawings on Thursday
            sim.khata.setdefault(sim.week_of(d), []).append([d, "Taken home for family expenses", rnd.choice([12000, 13000, 14000, 15000]), "expense", "Rana (owner)"])
        d += timedelta(days=1)


def season(k, d):
    m = 1.0
    if k in ("fan", "pfan"):
        m = 1.0 if d < date(2026, 9, 21) else 0.35
    if k in ("w15", "w25", "mcb", "switch", "tape") and d >= date(2026, 10, 1):
        m = 1.25  # construction picks up after the rains
    if k in ("led12", "led18", "tube", "elight") and date(2026, 10, 10) <= d <= date(2026, 10, 18):
        m = 1.4  # Durga Puja lighting
    if k in ("fairy", "strip"):
        m = 1.0 if d >= date(2026, 10, 16) else 0.0
    if k == "heater":
        m = 0.6 if d < date(2026, 10, 15) else 1.0
    if k == "elight":
        m = 1.0 if d >= date(2026, 9, 19) else 0.0
    return m


def day_sales(d):
    t = 10 * 60 + 40
    for k, (name, unit, cost, price, *_rest) in ITEMS.items():
        chance, (lo, hi) = ITEMS[k][6], ITEMS[k][7]
        if rnd.random() > chance * season(k, d):
            continue
        q = sim.sell_cap(k, rnd.randint(lo, hi))
        if q <= 0:
            continue
        price_each = price - (rnd.choice([0, 0, 0, 50, 100]) if price > 2000 else 0)
        amt = round(q * price_each, -1)
        ch = "bkash" if rnd.random() < .27 else "cash"
        word = SHORT[k] + ("s" if q > 1 and not SHORT[k].endswith("s") and not SHORT[k].startswith("coil") else "")
        word = word.replace("coil ", "coils " if q > 1 else "coil ")
        text = rnd.choice([f"sold {q} {word} {amt:.0f} {ch}", f"{q} {word} sold for {amt:.0f} tk {ch}",
                           f"sale {q} {word} {amt:.0f} taka {ch}"])
        t += rnd.randint(8, 55)
        sim.entries.append(dict(date=d, text=text, amount=amt, dir="in", cat="sales", channel=ch, item=k, qty=q,
                                party="Walk-in customer", ts=at(d, f"{min(t, 21*60) // 60:02d}:{min(t, 21*60) % 60:02d}")))
        sim.moves.append((k, -q, "sale", d, len(sim.entries) - 1))


def day_khata(d):
    w = sim.week_of(d)
    rows = sim.khata.setdefault(w, [])
    rows.append([d, "Counter sales - screws, plugs, holders, small items", round(rnd.uniform(3500, 8200), -1), "income", "Walk-in customers"])
    rows.append([d, "Tea and snacks for shop and customers", rnd.randint(8, 22) * 10, "expense", ""])
    if rnd.random() < .6:
        rows.append([d, "Van delivery to customer site", rnd.choice([200, 250, 300, 400, 500, 600]), "expense", "Van driver"])
    if d.day == 1:
        rows.append([d, "Sent to parents in Cumilla (bKash)", 15000, "expense", "Abba"])
        rows.append([d, "Children school fees", 9500, "expense", "School"])
        rows.append([d, "Salary - Jamal (shop assistant)", 12000, "expense", "Jamal"])
        rows.append([d, "Salary - Sujon (helper)", 10000, "expense", "Sujon"])
    if d.day in (5, 6) and not any("Godown" in r[1] and r[0].month == d.month for r in rows):
        rows.append([d, "Godown rent - Bangshal", 8000, "expense", "Godown owner"])
    if d.day == 10:
        rows.append([d, "Market committee monthly fee", 500, "expense", "Nawabpur Traders Samity"])
    if d.day == 12:
        rows.append([d, "DPDC electricity bill (paid by bKash)", rnd.choice([3650, 3820, 4100]), "expense", "DPDC"])
        rows.append([d, "Internet bill", 800, "expense", "Local ISP"])
    if d.weekday() == 0:
        rows.append([d, "Mobile recharge", 300, "expense", ""])
    if d.weekday() == 5:  # small items restocked every Saturday from Nawabpur wholesalers
        rows.append([d, "Small items purchase - screws, plugs, holders, clips", round(rnd.uniform(26000, 34000), -2), "expense", "Nawabpur wholesalers"])
    if d in (date(2026, 10, 2), date(2026, 10, 9), date(2026, 10, 16)):
        rows.append([d, "Facebook page boost - Rana Electric", 1500, "expense", "Meta"])


def bank_fixed():
    for d in (date(2026, 9, 5), date(2026, 10, 5)):
        sim.bank.append([d, f"CHQ to {LANDLORD} - shop rent", 32000, ""])
    sim.bank.append([date(2026, 9, 30), "Account maintenance fee and SMS charge", 575, ""])
    sim.bank.append([LOAN_DAY, f"SME term loan disbursement - TL/NWB/2026/0512", "", LOAN_AMT])
    sim.bank.append([LOAN_DAY, "Loan processing fee TL/NWB/2026/0512", LOAN_FEE, ""])
    sim.bank.append([LOAN_DAY, "VAT on processing fee", 900, ""])
    # One receipt also recorded in the app by hand (Al-Amin, 26 Sep) - should be flagged as a duplicate.
    al = next(c for c in CREDIT if c[0] == "RE-0002")
    sim.bank.append([date(2026, 9, 26), f"NPSB credit from AL-AMIN CONSTRUCTION ref {al[0]}", "", invoice_total(al)])
    sim.bank.sort(key=lambda r: r[0])


def bkash_fb_orders():
    d = date(2026, 10, 3)
    n = 1
    bal = 6200.0
    while d <= date(2026, 10, 18):
        for _ in range(rnd.randint(0, 2)):
            amt = float(rnd.choice([850, 1200, 1700, 2200, 2750, 3400, 4300]))
            bal += amt
            sim.bkash.append([f"{d.isoformat()} {rnd.randint(11, 21)}:{rnd.randint(10, 59)}:00", f"BKF{71200 + n}",
                              "Received Money", f"01{rnd.choice([3, 7, 8, 9])}{rnd.randint(10000000, 99999999)}", amt, 0, bal, "Success"])
            n += 1
        if d.weekday() == 2:
            bal -= 120
            sim.bkash.append([f"{d.isoformat()} 17:05:00", f"BKF{71200 + n}", "Payment", "Pathao Courier", 120, 0, bal, "Success"])
            n += 1
        d += timedelta(days=1)


def invoice_total(c):
    return float(sum(ITEMS[k][3] * q for k, q in c[5].items()))


# ----------------------------------------------------------------------------- audit (chronological, hash-chained)
AUDIT: list[dict] = []


def aud(ts, event_type, action, tier=None, inputs=None, result=None, confirmation="not_required", rid=None):
    AUDIT.append(dict(ts=ts, event_type=event_type, action=action, tier=tier, inputs=inputs or {}, result=result or {},
                      confirmation_status=confirmation, request_id=rid or uuid.uuid4().hex[:16]))


def write_audit(db, bid):
    prev = GENESIS
    last = db.scalar(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1))
    if last is not None:
        prev = last.hash
    for e in sorted(AUDIT, key=lambda x: x["ts"]):
        ev = AuditEvent(ts=e["ts"], business_id=bid, actor=USER, actor_role="owner", event_type=e["event_type"],
                        action=e["action"], tier=e["tier"], inputs=_jsonable(mask_obj(e["inputs"])),
                        result=_jsonable(mask_obj(e["result"])), confirmation_status=e["confirmation_status"],
                        request_id=e["request_id"], prev_hash=prev, hash="")
        ev.hash = compute_hash(prev, _event_dict(ev))
        db.add(ev)
        db.flush()
        prev = ev.hash


# ----------------------------------------------------------------------------- chats
def chats(sales_week, cash_on):
    """(date, time, [(role, text, tools)]). Assistant numbers use the generated books."""
    w1 = sales_week(date(2026, 8, 20), date(2026, 8, 26))
    w_sep = sales_week(date(2026, 9, 14), date(2026, 9, 20))
    w_drop = sales_week(date(2026, 9, 21), date(2026, 9, 27))
    def fans(lo, hi):
        return sum(e["qty"] for e in sim.entries if e["item"] in ("fan", "pfan") and lo <= e["date"] <= hi)
    fans_aug, fans_sep, fans_drop = fans(date(2026, 8, 20), date(2026, 8, 26)), fans(date(2026, 9, 14), date(2026, 9, 20)), fans(date(2026, 9, 21), date(2026, 9, 27))
    return [
        (date(2026, 8, 20), "11:05", [
            ("user", "Assalamualaikum. I have an electric and hardware shop in Nawabpur. How do I use this app?", []),
            ("assistant", "Walaikum assalam, Rana bhai. Three simple steps:\n1. Tell me how much business money you have today (cash + bank + bKash). That is your starting point.\n2. Each day, type what you sold or spent, like \"sold 2 ceiling fan 7000 cash\". I will add it to your records.\n3. Once a week, upload your khata or bank statement and I will match everything.\nYour Home screen will then show your money and one next step. What is your total business money today?", []),
            ("user", "cash 55,000 bank e 58,000 bkash 7,000", []),
            ("assistant", f"Saved. Your starting business money is {tk(OPENING)} on 19 Aug 2026: cash {tk(55000)}, bank {tk(58000)}, bKash {tk(7000)}. From now on every sale and expense moves this number.", ["record_opening_balance"]),
        ]),
        (date(2026, 8, 27), "21:40", [
            ("user", "how much did i sell this week", []),
            ("assistant", f"From 20 to 26 Aug you recorded {tk(w1)} in sales (typed sales plus your khata). Ceiling fans and LED bulbs brought in the most money. You also gave {tk(38380)} of goods on credit to Babul Electric Works, due 8 Sep. That is not cash yet.", ["get_profitability"]),
            ("user", "is this good or bad?", []),
            ("assistant", "It is your first week, so there is nothing to compare yet. After 4 weeks I can tell you which items earn the most profit, not only the most sales. For now, keep typing the big items (fans, drills, wire coils) with the quantity, so stock is counted too.", []),
        ]),
        (date(2026, 8, 30), "22:15", [
            ("user", "Bhai how can I grow my business? Nawabpur e onek competition, 20 ta same dokan", []),
            ("assistant", "With many similar shops, growth usually comes from customers who come back, not from lower prices. Ideas that fit your records:\n1. Electricians and contractors: Babul and Al-Amin already buy big amounts on credit. Give 2-3 regular contractors a monthly account with a clear limit and due date. They bring repeat orders.\n2. Keep the fast items always in stock: LED bulbs, switch boards, tape and 1.5 rm wire sell almost every day. A customer who finds them out of stock goes to the next shop.\n3. Package deals: \"flat wiring kit\" (wire + MCB + switch boards) for contractors, at one price.\n4. A Facebook page or WhatsApp list with today's price of fans and wire. Many buyers check prices before coming to Nawabpur.\nThis is general guidance, not a guarantee. Want me to turn one of these into a task?", []),
            ("user", "1 number ta better. kintu baki dile taka atke jay", []),
            ("assistant", "True, credit is only good if it comes back on time. Simple rules: a written limit per contractor (for example 50,000), 15-30 days to pay, no new goods if the last bill is overdue, and a polite reminder on the due date. I can track every customer's due date and remind you.", []),
        ]),
        (date(2026, 9, 2), "20:50", [
            ("user", "I want to take a loan of 5 lakh to buy more stock before winter and wedding season. bank or NGO which is better?", []),
            ("assistant", "A loan can help if the extra stock sells before the instalments become heavy. Before choosing a lender, compare the full cost, not only the interest rate:\n- Bank SME loans: usually lower total cost, but need a trade licence, TIN, bank statements and often a guarantor. Takes 2-4 weeks.\n- NGO / MFI loans: faster and fewer papers, but weekly instalments and a higher effective cost.\nWhat to do now: ask 2 lenders for a written quote with the amount, every fee, and every repayment date. When you have them, open AI Assistant > Check a loan quote and I will test each quote against your cash, including slow months.\nI cannot approve or recommend a specific lender; I can check the numbers.", []),
            ("user", "my bank is Karnaphuli Commercial Bank nawabpur branch. what will they ask?", []),
            ("assistant", "Usually: trade licence (valid), TIN certificate, NID, 6-12 months bank statement, a few months of sales and expense records, a stock list, and sometimes a guarantor and a photo of the shop. You have a trade licence and TIN on file. Your records in this app start 20 Aug, so by the time you apply you will have about 1 month of clean books. I can prepare a loan-readiness report from them.", ["compliance_info"]),
        ]),
        (date(2026, 9, 6), "10:20", [
            ("user", "Babul Electric owes me 38380 since 25 aug, due date passed. write a polite reminder", []),
            ("assistant", "Babul Electric Works: bill RE-0001, ৳38,380, due 8 Sep (2 days overdue). Here is a polite reminder. I saved it in Documents, and nothing is sent until you confirm.", ["find_invoice", "draft_invoice_followup"]),
            ("user", "ok also send sms reminder tomorrow", []),
            ("assistant", "Reminder scheduled for 7 Sep to Babul Electric Works for ৳38,380. (SMS sending is simulated in this pilot; the reminder also shows in your Tasks.)", ["create_payment_reminder"]),
        ]),
        (date(2026, 9, 9), "22:30", [
            ("user", "please write a letter to bank manager for SME loan 5 lakh. purpose buying stock for winter. I have shop 9 years", []),
            ("assistant", "I wrote a formal application to the Branch Manager, Karnaphuli Commercial Bank PLC, Nawabpur Road Branch, for an SME loan of ৳5,00,000 for working capital (stock). It mentions your business since 2017, your trade licence and TIN, your regular contractor customers and that you can share bank statements and a stock list. Check the details in Documents, sign it, and attach copies of your papers.", ["draft_letter"]),
            ("user", "add that i can give my shop stock as security", []),
            ("assistant", "Added a line offering hypothecation of shop stock as security, subject to the bank's terms. The updated letter is in Documents.", ["update_draft"]),
        ]),
        (date(2026, 9, 12), "19:10", [
            ("user", "what papers do i need to bring for the loan? make a list", []),
            ("assistant", "Here is your checklist (saved in Documents):\nHave: trade licence, TIN certificate, NID, bank account.\nCan generate here: loan-readiness report with your sales, expenses, credit customers and 90-day cash forecast.\nTo prepare: 6 months bank statement (from the bank), stock list with values, 2 passport photos, guarantor's NID, shop rent agreement.\nI also generated a loan-readiness report from your records; you can download it in Reports.", ["prepare_loan_checklist", "generate_loan_report"]),
        ]),
        (date(2026, 9, 15), "21:05", [
            ("user", "load shedding is back. should i sell rechargeable emergency light? supplier gives 650 each, sell 950", []),
            ("assistant", "It can work as a small test. I opened a guided task: Try a new product. Start with a small batch (around 20 pieces) so your money is not stuck if they do not sell. At ৳950 selling and ৳650 cost you keep about ৳300 each before transport. Let's go through the questions.", ["start_guided_task:stock"]),
        ]),
        (date(2026, 9, 18), "09:45", [
            ("user", "set appointment: meeting with bank SME officer on 24 september 11 am. remind me", []),
            ("assistant", "Saved: \"Meeting with SME officer, Karnaphuli Commercial Bank, Nawabpur Road Branch\" on 24 Sep at 11:00. It will show in Tasks > Coming up, and on Home on the day. Bring: trade licence, TIN, NID, the loan letter and the loan-readiness report.", ["add_reminder"]),
        ]),
        (date(2026, 9, 24), "16:30", [
            ("user", "meeting done. bank says they can give 4 lakh not 5, 24 months, they will send written offer. they want stock statement every month", []),
            ("assistant", "Good progress. When the written offer arrives, enter it in Check a loan quote: amount, all fees, and every instalment date. I will test it against a normal month and a slow month. For the monthly stock statement, your Stock page can export the current list with quantities and cost.", []),
            ("user", "update the letter to 4 lakh", []),
            ("assistant", "Updated: a revised application for ৳4,00,000, referring to today's meeting and offering a monthly stock statement. Saved in Documents.", ["draft_letter"]),
        ]),
        (date(2026, 9, 28), "22:00", [
            ("user", "fan sales down this week. why? should I worry?", []),
            ("assistant", f"You sold {fans_drop} fans (ceiling and pedestal) from 21 to 27 Sep, compared with {fans_sep} the week before and {fans_aug} in your first week. That is the season: demand for fans falls as the weather cools. Your total sales that week were {tk(w_drop)} against {tk(w_sep)} the week before, so the shop as a whole is {'doing better' if w_drop >= w_sep else 'a little slower'}: wire, MCB, switch boards and the new emergency lights made up for the fans. No need to worry, but buy fewer fans until March and put that money into wire and lighting for the construction and Puja season.", ["explain_change"]),
        ]),
        (date(2026, 10, 1), "21:20", [
            ("user", "how to grow more? young customers search online. should i sell on facebook?", []),
            ("assistant", "Yes, a simple start costs little:\n1. A Facebook page \"Rana Electric & Hardware, Nawabpur\" with photos and prices of your 15 best items. Update fan, wire and bulb prices weekly.\n2. Take orders by bKash. Deliver within Old Dhaka by van or Pathao, and add the delivery charge.\n3. A small boost (৳1,000-1,500 a week) aimed at electricians and new flat owners in Dhaka South.\n4. Track it: I will show Facebook orders separately when you upload your bKash statement, so you can see if the boost pays for itself.\nTry it for 4 weeks, then we compare.", []),
        ]),
        (date(2026, 10, 4), "20:40", [
            ("user", "Bank sent offer: 4,00,000, processing fee 6000 + vat, 24 months, kisti 18850 per month from 6 november. can i afford?", []),
            ("assistant", "__LOAN2__", ["start_guided_task:loan"]),
        ]),
        (date(2026, 10, 7), "11:10", [
            ("user", "loan money came yesterday 4 lakh. add the kisti to my payments", []),
            ("assistant", "Added: Loan EMI to Karnaphuli Commercial Bank, ৳18,850 every month on the 6th, from 6 Nov 2026 to 6 Oct 2028. It now appears in Money ahead and in your cash forecast. I also see the ৳4,00,000 disbursement and the ৳6,900 fee and VAT on your bank statement.", ["add_obligation"]),
            ("user", "i paid 80000 to rahman cable from it", []),
            ("assistant", "Recorded the sandbox payment of ৳80,000 to Rahman Cable Traders against bill RCT-0917. ৳71,200 is still due on that bill.", ["pay_supplier_invoice"]),
        ]),
        (date(2026, 10, 11), "21:35", [
            ("user", "which items are running low?", []),
            ("assistant", "From your stock records: MCB circuit breaker 32A is almost out, and switch boards are selling fast. You have enough ceiling fans now that fan demand has dropped. LED bulbs and tube lights are fine after this week's order. Rechargeable emergency lights sold well: you have sold most of the second batch. Restocking the low items to a safe level would cost about ৳20,000-25,000.", ["get_stock"]),
        ]),
        (date(2026, 10, 14), "18:25", [
            ("user", "Rahman Cable needs 71200 by 30 oct but shahjahan builders has not paid me. write a letter asking 15 days more", []),
            ("assistant", "Here is a polite request to Rahman Cable Traders for 15 more days (until 14 Nov 2026) on bill RCT-0917, ৳71,200 outstanding. It mentions your long relationship, the ৳80,000 you paid on 7 Oct, and that you are waiting for a contractor payment. Saved in Documents.", ["draft_letter"]),
            ("user", "and write a strong reminder to shahjahan builders", []),
            ("assistant", "Shahjahan Builders: bill RE-0004, ৳51,450 still due since 3 Oct. I wrote a firm but polite reminder asking for payment by 21 Oct, and noted that new orders depend on settling this bill. Saved in Documents. Do you want an SMS reminder too?", ["draft_invoice_followup"]),
            ("user", "yes", []),
            ("assistant", "SMS reminder scheduled for 15 Oct to Shahjahan Builders for ৳51,450.", ["create_payment_reminder"]),
        ]),
        (date(2026, 10, 17), "22:10", [
            ("user", "winter is coming. what should i stock? and wedding season lighting?", []),
            ("assistant", "From your own sales: room heaters have started selling (you bought 15 on 8 Oct). Ideas for Nov-Jan:\n1. Room heaters and water heater rods: small batches, reorder when half is sold.\n2. Wedding and decoration lights: fairy lights and LED strips sell from late November. Ask Bright Light Wholesale for sale-or-return terms on the first batch.\n3. Keep wire, MCB and switch boards fully stocked: construction work is busy in winter, and your contractors are your biggest buyers.\n4. Reduce fan orders until March.\nWatch your cash: the first loan instalment of ৳18,850 is due 6 Nov and Rahman Cable's ৳71,200 on 30 Oct. A new-product test would show how much you can safely spend.", []),
        ]),
        (date(2026, 10, 19), "09:15", [
            ("user", "good morning. what should i do today?", []),
            ("assistant", "Good morning, Rana bhai. One thing first today: call Shahjahan Builders about ৳51,450 that is 16 days overdue. You need it before Rahman Cable's bill on 30 Oct. After that: Al-Amin Construction's ৳33,450 was due 17 Oct, and Babul Electric Works has ৳27,550 overdue since 5 Oct.", ["get_alerts"]),
        ]),
    ]


LETTERS = {
    "loan_letter_1": (date(2026, 9, 9), "loan_application", "The Branch Manager, Karnaphuli Commercial Bank PLC, Nawabpur Road Branch",
        "Application for SME working-capital loan of Tk 5,00,000",
        """Date: 09 September 2026

To
The Branch Manager
Karnaphuli Commercial Bank PLC
Nawabpur Road Branch, Dhaka-1100

Subject: Application for an SME working-capital loan of Tk 5,00,000 (five lakh taka)

Dear Sir,

I, Md. Rana Hossain, am the proprietor of Rana Electric & Hardware, 112 Nawabpur Road, Dhaka-1100. I have run this shop since March 2017, selling electrical goods and hardware: wire, MCBs, switch boards, LED lights, fans and power tools. I have held a current account (CD-0021-778812) at your branch for several years.

My customers include walk-in buyers and regular electricians and building contractors in Old Dhaka, Jatrabari and Keraniganj. Before the winter and wedding season, demand for wire, lighting, tools and heaters rises, and contractors place larger orders. I request a working-capital loan of Tk 5,00,000 to buy this stock in time.

I can provide:
1. Valid trade licence (Dhaka South City Corporation)
2. TIN certificate
3. National ID card
4. Bank statement of my current account
5. Monthly sales, expense and customer-credit records, and a current stock list with values

As security, I can offer hypothecation of my shop stock, subject to the bank's terms.

I request you to kindly consider my application and let me know the terms, charges and further documents required.

Sincerely,

__________________
Md. Rana Hossain
Proprietor, Rana Electric & Hardware
112 Nawabpur Road, Dhaka-1100
Mobile: 01711-XXXXXX"""),
    "loan_letter_2": (date(2026, 9, 24), "loan_application", "The Branch Manager, Karnaphuli Commercial Bank PLC, Nawabpur Road Branch",
        "Revised application: SME loan of Tk 4,00,000",
        """Date: 24 September 2026

To
The Branch Manager
Karnaphuli Commercial Bank PLC
Nawabpur Road Branch, Dhaka-1100

Subject: Revised application for an SME working-capital loan of Tk 4,00,000

Dear Sir,

With reference to my application dated 09 September 2026 and today's meeting with your SME officer, I would like to revise my request to Tk 4,00,000 (four lakh taka), repayable in 24 monthly instalments, as discussed.

The loan will be used to buy stock for the winter and construction season: wire, circuit breakers, lighting, power tools and room heaters. I agree to submit a stock statement every month and to keep my business transactions through my current account at your branch.

The documents requested at the meeting (trade licence, TIN certificate, NID, bank statement, stock list and the loan-readiness report from my records) are attached.

Kindly send the written offer with all charges and the repayment schedule.

Sincerely,

__________________
Md. Rana Hossain
Proprietor, Rana Electric & Hardware"""),
    "bank_thanks": (date(2026, 10, 7), "bank_letter", "The Branch Manager, Karnaphuli Commercial Bank PLC, Nawabpur Road Branch",
        "Request for standing instruction for monthly loan instalment",
        """Date: 07 October 2026

To
The Branch Manager
Karnaphuli Commercial Bank PLC
Nawabpur Road Branch, Dhaka-1100

Subject: Standing instruction for monthly instalment of loan TL/NWB/2026/0512

Dear Sir,

Thank you for disbursing my SME term loan of Tk 4,00,000 on 06 October 2026.

I request you to debit the monthly instalment of Tk 18,850 from my current account CD-0021-778812 on the 6th of every month, starting 06 November 2026, until the loan is fully repaid. Please also send me the full repayment schedule.

Sincerely,

__________________
Md. Rana Hossain
Proprietor, Rana Electric & Hardware"""),
    "rahman_ext": (date(2026, 10, 14), "supplier_letter", "Rahman Cable Traders",
        "Request for 15 more days on bill RCT-0917",
        """Date: 14 October 2026

To
The Proprietor
Rahman Cable Traders
Nawabpur, Dhaka

Subject: Request for 15 more days to pay bill RCT-0917

Dear Bhai,

Assalamualaikum. Thank you for supplying wire, MCBs and tape on credit for many years.

On 07 October I paid Tk 80,000 against bill RCT-0917 (dated 05 September 2026). The remaining Tk 71,200 is due on 30 October. One of my building contractors has delayed a large payment, so I request 15 more days, until 14 November 2026, to pay the balance in full.

I will keep you informed and pay earlier if the contractor pays sooner. I hope you will kindly agree.

Regards,

Md. Rana Hossain
Rana Electric & Hardware, 112 Nawabpur Road"""),
}

FOLLOWUPS = [  # (date, invoice_no, tone, language, subject, body, status)
    (date(2026, 9, 6), "RE-0001", "polite", "en", "Payment reminder - bill RE-0001",
     "Dear Babul bhai,\n\nAssalamualaikum. Our records show bill RE-0001 dated 25 Aug 2026 for Tk 38,380 (wire, MCB and switch boards for the Jatrabari flat). It was due on 8 Sep.\n\nPlease let me know when you can pay. bKash or cash at the shop is fine.\n\nThank you,\nRana\nRana Electric & Hardware", "approved"),
    (date(2026, 10, 14), "RE-0004", "firm", "en", "Overdue payment - bill RE-0004 (Tk 51,450)",
     "Dear Shahjahan Sahib,\n\nAssalamualaikum. Thank you for the part payment of Tk 60,000 on 1 Oct. Tk 51,450 is still due on bill RE-0004 (dated 3 Sep 2026), which was due on 3 Oct.\n\nPlease pay the balance by 21 October 2026. I need to pay my own supplier this month, and I can deliver new orders for the Keraniganj building once this bill is settled.\n\nRegards,\nMd. Rana Hossain\nRana Electric & Hardware", "draft"),
    (date(2026, 10, 16), "RE-0005", "polite", "bn", "বাকি টাকার বিষয়ে - বিল RE-0005",
     "প্রিয় কামাল ভাই,\n\nআসসালামু আলাইকুম। ৮ সেপ্টেম্বরের বিল RE-0005-এ ৬,৮১০ টাকা বাকি আছে। আপনি বলেছেন একটি ড্রিল বিট সেট ফেরত দিয়েছেন। চলুন একদিন দোকানে বসে বিলটা মিলিয়ে নিই, তারপর বাকি টাকা ঠিক করি।\n\nধন্যবাদ,\nরানা", "draft"),
]

APPOINTMENTS = [  # (created, due, title, message, status)
    (at(date(2026, 9, 18), "09:46"), date(2026, 9, 24), "Meeting: SME officer, Karnaphuli Commercial Bank (11:00)",
     "Nawabpur Road Branch. Bring trade licence, TIN, NID, loan letter and loan-readiness report.", "acknowledged"),
    (at(date(2026, 10, 4), "21:00"), date(2026, 10, 6), "Bank: sign loan documents (10:30)",
     "Karnaphuli Commercial Bank. Bring guarantor (Faruk mama) with NID and 2 photos.", "acknowledged"),
    (at(date(2026, 10, 14), "18:40"), date(2026, 10, 21), "Collect cheque from Shahjahan Builders (৳51,450)",
     "Keraniganj site office. Call before going.", "scheduled"),
    (at(date(2026, 10, 17), "22:20"), date(2026, 10, 24), "Meet Chawkbazar Tools Import: winter order",
     "Ask about heater and water-heater rod prices, sale-or-return for fairy lights.", "scheduled"),
    (at(date(2026, 10, 7), "11:20"), date(2026, 11, 5), "Submit monthly stock statement to bank",
     "Export Stock list and take it to the SME desk before the 6 Nov instalment.", "scheduled"),
]


# ----------------------------------------------------------------------------- build
def main():
    s = get_settings()
    db_path = s.data_dir / "copilot.db"
    reset_engine()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = db_path.with_name(db_path.name + suffix)
        if p.exists():
            p.unlink()
    for f in (s.reports_dir.glob("*.pdf") if s.reports_dir.exists() else []):
        f.unlink()
    init_db()

    run_sim()
    bank_fixed()
    bkash_fb_orders()

    db = SessionLocal()
    created = at(START, "10:52")
    b = Business(name="Rana Electric & Hardware", sector="electrical and hardware shop", district="Dhaka",
                 owner_name="Md. Rana Hossain", established_on=date(2017, 3, 1),
                 trade_license_no="TRAD/DSCC/045812/2017", tin="447122903381", has_trade_license=True, has_tin=True,
                 vat_registered=False, has_bank_account=True, women_led=False, collateral_value=0,
                 existing_monthly_debt_service=EMI, opening_cash_balance=OPENING,
                 opening_balance_date=START - timedelta(days=1), low_balance_threshold=80_000,
                 prefs={"number_style": "lakh", "language": "en",
                        "about": "Electrical and hardware shop on Nawabpur Road, Old Dhaka: drill machines, grinders, "
                                 "hand tools, wire coils, MCBs, switch boards, LED bulbs and tube lights, ceiling and "
                                 "pedestal fans. Walk-in customers plus electricians and building contractors on credit."},
                 created_at=created)
    db.add(b)
    db.flush()
    bid = b.id
    user = create_user(db, bid, USER, PASSWORD, "owner", "Md. Rana Hossain")
    user.created_at = created
    aud(created, "auth", "signup", inputs={"ip": IP, "username": USER})
    aud(created + timedelta(minutes=1), "auth", "login", inputs={"ip": IP})
    aud(created + timedelta(minutes=4), "operation", "business_setup", 1,
        inputs={"business_type": "retail", "district": "Dhaka", "opening_balance": OPENING})
    db.add(HomePrefs(user_id=user.id, business_id=bid, **hl.normalize_prefs(
        business_type=hl.type_key("retail", "electrical hardware shop"), mode="simplified", widgets=hl.SIMPLIFIED,
        nav=None, style="general")))
    db.add(MarketWatch(user_id=user.id, business_id=bid, items=watch.rule_pick(b.name, "retail", b.prefs["about"]),
                       source="rules", reason="electrical and hardware shop"))
    db.add(NotificationPreference(user_id=user.id, business_id=bid, phone="01711000000", consent=False,
                                  verified=False, language="en", send_hour=19))
    sbx = SandboxAccount(business_id=bid, name="Sandbox Operating Account", account_no=f"SBX-{bid:010d}", balance=300_000)
    db.add(sbx)
    db.flush()

    # items
    item_obj = {}
    for k, (name, unit, cost, price, opening, reorder, *_r, aliases) in ITEMS.items():
        it = Item(business_id=bid, name=name, aliases=aliases, unit=unit, opening_qty=opening, reorder_level=reorder,
                  cost_price=cost)
        db.add(it)
        item_obj[k] = it
    db.flush()
    aud(at(START, "11:30"), "operation", "create_item", 1, inputs={"count": len(ITEMS), "note": "opening stock list"})

    # obligations
    for name, cat, amount, day, nxt, end in (
            (f"Shop rent - {LANDLORD}", "rent", 32000, 5, date(2026, 11, 5), None),
            ("Godown rent - Bangshal", "rent", 8000, 5, date(2026, 11, 5), None),
            ("Staff salary (Jamal + Sujon)", "salary", 22000, 1, date(2026, 11, 1), None),
            ("DPDC electricity bill", "utilities", 3900, 12, date(2026, 11, 12), None),
            (f"Loan EMI - {BANK} TL/NWB/2026/0512", "loan_repayment", EMI, 6, date(2026, 11, 6), date(2028, 10, 6))):
        db.add(Obligation(business_id=bid, name=name, category=cat, amount=amount, day_of_month=day, next_due=nxt,
                          end_date=end, source="user", created_at=at(START, "11:40") if cat != "loan_repayment" else at(date(2026, 10, 7), "11:11")))
    aud(at(START, "11:40"), "operation", "add_obligation", 1, inputs={"names": ["Shop rent", "Godown rent", "Staff salary", "DPDC electricity"]})
    db.add(RecurringInvoice(business_id=bid, counterparty="Green View Apartments", description="Monthly building maintenance supplies",
                            amount=6500, frequency="monthly", day_of_month=1, next_issue=date(2026, 11, 1), due_days=9,
                            created_at=at(date(2026, 10, 1), "10:05")))
    aud(at(date(2026, 10, 1), "10:05"), "operation", "create_recurring", 1, inputs={"counterparty": "Green View Apartments", "amount": 6500})
    db.flush()

    # typed entries (quick entry) + their stock movements
    entry_txn = {}
    for i, e in enumerate(sim.entries):
        t = Transaction(business_id=bid, txn_date=e["date"], amount=e["amount"], direction=e["dir"], category=e["cat"],
                        counterparty=e["party"], description=e["text"], channel=e["channel"], quantity=e["qty"],
                        item=ITEMS[e["item"]][0], source="nl", categorized_by="rule", category_confidence=0.9,
                        created_at=e["ts"])
        db.add(t)
        db.flush()
        entry_txn[i] = t
        aud(e["ts"], "tool_call", "add_transaction", 1, inputs={"text": e["text"]},
            result={"recorded": True, "transaction_id": t.id, "linked_item": ITEMS[e["item"]][0]})
    for d, sup, items, total, ref in sim.cash_purchases:
        ts = at(d, "13:20")
        what = " and ".join(f"{q} {SHORT[k]}" for k, q in items.items())
        text = f"bought {what} from {sup} {total:.0f} cash"
        one = len(items) == 1
        k0, q0 = next(iter(items.items()))
        t = Transaction(business_id=bid, txn_date=d, amount=total, direction="out", category="inventory",
                        counterparty=sup, description=text, channel="cash", quantity=q0 if one else None,
                        item=ITEMS[k0][0] if one else "", source="nl", categorized_by="rule", created_at=ts)
        db.add(t)
        db.flush()
        entry_txn[ref] = t
        aud(ts, "tool_call", "add_transaction", 1, inputs={"text": text}, result={"recorded": True, "transaction_id": t.id})

    # customer invoices (created in the app) with lines, payments and stock
    inv_obj = {}
    for no, cust, phone, issue, due, items, pays, note in CREDIT:
        total = invoice_total((no, cust, phone, issue, due, items))
        inv = Invoice(business_id=bid, kind="receivable", invoice_no=no, counterparty=cust, counterparty_phone=phone,
                      amount=total, amount_paid=0, issue_date=issue, due_date=due, status="open", notes=note,
                      source="manual", created_at=at(issue, "15:30"))
        db.add(inv)
        db.flush()
        for k, q in items.items():
            db.add(InvoiceLine(invoice_id=inv.id, description=ITEMS[k][0], quantity=q, rate=ITEMS[k][3]))
        aud(at(issue, "15:30"), "operation", "create_invoice", 1, inputs={"invoice_no": no, "customer": cust, "amount": total})
        paid = 0.0
        for pd_, amt, ch in pays:
            amt = amt or (total - paid)
            ts = at(pd_, "17:10")
            t = Transaction(business_id=bid, txn_date=pd_, amount=amt, direction="in", category="sales", counterparty=cust,
                            description=f"Payment for {no}", channel=ch, reference=no, source="invoice_payment",
                            categorized_by="user", created_at=ts)
            db.add(t)
            db.flush()
            db.add(InvoicePayment(business_id=bid, invoice_id=inv.id, amount=amt, paid_on=pd_, channel=ch,
                                  transaction_id=t.id, created_by=USER, created_at=ts))
            paid += amt
            aud(ts, "operation", "record_invoice_payment", 1, inputs={"invoice_no": no, "amount": amt, "channel": ch})
        inv.amount_paid = paid
        inv.status = "paid" if paid >= total - 0.01 else ("partial" if paid else "open")
        inv.paid_date = pays[-1][0] if inv.status == "paid" else None
        inv_obj[no] = inv
    db.flush()

    # supplier bills (payables) - created in the app
    for no, sup, total, issue, due, paid_now, desc in sim.bills:
        inv = Invoice(business_id=bid, kind="payable", invoice_no=no, counterparty=sup, amount=total, amount_paid=0,
                      issue_date=issue, due_date=due, status="open", notes=desc + (" (due date extended from 5 Oct after request)" if no == "RCT-0917" else ""),
                      source="manual", created_at=at(issue, "18:00"))
        db.add(inv)
        db.flush()
        inv_obj[no] = inv
        aud(at(issue, "18:00"), "operation", "create_invoice", 1, inputs={"invoice_no": no, "supplier": sup, "amount": total, "kind": "payable"})
        if paid_now:
            inv.amount_paid = paid_now
            inv.status = "partial"
    db.flush()

    # weekly khata uploads, then bank + bKash statements, through the real importer
    imports = []
    for wk, rows in sorted(sim.khata.items()):
        rows.sort(key=lambda r: r[0])
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["Date", "Description", "Amount", "Type", "Party"])
        w.writerows([[dmy(r[0]), r[1], r[2], r[3], r[4]] for r in rows])
        up = wk if wk.weekday() != 4 else wk + timedelta(days=1)
        imports.append((at(up, "21:45"), f"khata_week_{rows[0][0]:%d%b}-{rows[-1][0]:%d%b}.csv".lower(), "ledger", buf.getvalue()))
    for label, lo, hi, up in (("aug-sep", START, date(2026, 9, 30), date(2026, 10, 2)), ("oct", date(2026, 10, 1), date(2026, 10, 17), date(2026, 10, 18))):
        buf = io.StringIO()
        buf.write(f"{BANK}\nStatement of Account - {BRANCH}\nAccount Name: RANA ELECTRIC & HARDWARE\nAccount No: CD-0021-778812\n"
                  f"Period: {dmy(lo)} to {dmy(hi)}\n\n")
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["Txn Date", "Narration", "Withdrawal", "Deposit"])
        w.writerows([[dmy(r[0]), r[1], r[2], r[3]] for r in sim.bank if lo <= r[0] <= hi])
        imports.append((at(up, "22:05"), f"kcb_statement_{label}.csv", "bank", buf.getvalue()))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Date", "Trx ID", "Transaction Type", "Counterparty", "Amount", "Fee", "Balance", "Status"])
    w.writerows(sim.bkash)
    imports.append((at(date(2026, 10, 18), "22:12"), "bkash_statement_oct.csv", "wallet", buf.getvalue()))

    import_reports = {}
    for ts, name, doc, content in imports:
        rep = import_file(db, bid, content.encode("utf-8"), name, doc_type=doc, actor=USER)
        r = rep.to_dict()
        summary = {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()
                   if k in ("doc_type", "rows_total", "imported", "duplicates", "anomalies", "injection_flags", "errors")}
        import_reports[name] = summary
        db.execute(update(ImportBatch).where(ImportBatch.id == rep.batch_id).values(created_at=ts))
        db.execute(update(Transaction).where(Transaction.batch_id == rep.batch_id).values(created_at=ts))
        aud(ts, "operation", "import_file", 1, inputs={"filename": name, "doc_type": doc}, result=summary)
    db.flush()

    # stock movements: sales/purchases linked to their records where one exists
    bank_purchase = {}
    for t in db.scalars(select(Transaction).where(Transaction.business_id == bid, Transaction.source.like("%kcb_statement%"))):
        ref = sim.bank_refs.get((t.txn_date, float(t.amount)))
        if ref:
            bank_purchase[ref] = t
    for k, q, reason, d, ref in sim.moves:
        txn = entry_txn.get(ref)
        if txn is None and str(ref).startswith("PUR-"):
            txn = bank_purchase.get(ref)
        m = StockMovement(item_id=item_obj[k].id, qty_change=float(q), reason=reason,
                          transaction_id=txn.id if txn is not None else None, created_at=at(d, "12:00"))
        db.add(m)
    for ts_d, k, q in ((date(2026, 9, 30), "led12", -6), (date(2026, 10, 15), "tube", -2)):
        db.add(StockMovement(item_id=item_obj[k].id, qty_change=q, reason="adjust", created_at=at(ts_d, "20:30")))
        aud(at(ts_d, "20:30"), "operation", "adjust_stock", 1, inputs={"item": ITEMS[k][0], "change": q, "reason": "broken in shop"})
    db.flush()

    # sandbox payments (confirmed, with step-up), one failed attempt
    def sandbox_pay(when, bill_no, amount, typed=None, reject=False):
        inv = inv_obj[bill_no]
        pa = PendingAction(business_id=bid, user_id=user.id, tool="pay_supplier_invoice",
                           args={"invoice_id": inv.id, "amount": amount}, tier=2,
                           summary=f"Pay {tk(amount)} to {inv.counterparty} for invoice {bill_no} from the sandbox account",
                           amount=amount, recipient=inv.counterparty, status="rejected" if reject else "confirmed",
                           origin="agent", request_id=uuid.uuid4().hex[:16], result={}, created_at=when,
                           expires_at=when + timedelta(minutes=15), decided_at=when + timedelta(minutes=2), decided_by=USER)
        db.add(pa)
        db.flush()
        aud(when, "tool_call", "pay_supplier_invoice", 2, inputs={"invoice_no": bill_no, "amount": amount},
            result={"status": "pending_confirmation", "pending_action_id": pa.id}, confirmation="pending", rid=pa.request_id)
        if typed is not None:
            aud(when + timedelta(minutes=1), "security", "confirm_amount_mismatch", 2,
                inputs={"pending_action_id": pa.id, "typed_amount": typed}, result={"expected": amount},
                confirmation="rejected", rid=pa.request_id)
        if reject:
            aud(when + timedelta(minutes=2), "operation", "pay_supplier_invoice", 2, inputs={"pending_action_id": pa.id},
                result={"status": "rejected"}, confirmation="rejected", rid=pa.request_id)
            return
        sbx.balance = round(float(sbx.balance) - amount, 2)
        st = SandboxTransfer(business_id=bid, account_id=sbx.id, kind="invoice_payment", recipient_name=inv.counterparty,
                             amount=amount, purpose=f"Invoice {bill_no}", invoice_id=inv.id, status="executed",
                             pending_action_id=pa.id, balance_after=sbx.balance, executed_at=when + timedelta(minutes=2),
                             created_at=when)
        db.add(st)
        t = Transaction(business_id=bid, txn_date=(when + timedelta(hours=6)).date(),
                        amount=amount, direction="out", category="inventory", counterparty=inv.counterparty,
                        description=f"[sandbox] Invoice {bill_no}", channel="bank", reference=f"SBX-{pa.id}",
                        source="sandbox", flags=["sandbox"], created_at=when + timedelta(minutes=2))
        db.add(t)
        inv.amount_paid = float(inv.amount_paid) + amount
        inv.status = "paid" if inv.amount_paid >= float(inv.amount) - .01 else "partial"
        inv.paid_date = t.txn_date if inv.status == "paid" else None
        pa.result = {"transfer_id": None, "status": "executed", "balance_after": sbx.balance}
        aud(when + timedelta(minutes=2), "operation", "pay_supplier_invoice", 2, inputs={"pending_action_id": pa.id, "amount": amount},
            result={"status": "executed", "balance_after": sbx.balance}, confirmation="confirmed", rid=pa.request_id)

    sandbox_pay(at(date(2026, 9, 21), "12:30"), "DFA-2231", purchase_value({"fan": 30, "pfan": 10}))
    sandbox_pay(at(date(2026, 10, 7), "11:30"), "RCT-0917", 80000, typed=8000)
    sandbox_pay(at(date(2026, 10, 9), "20:10"), "CTI-3308", 30150, reject=True)
    # one still waiting for him today
    pa = PendingAction(business_id=bid, user_id=user.id, tool="pay_supplier_invoice",
                       args={"invoice_id": inv_obj["BLW-5520"].id, "amount": 20000}, tier=2,
                       summary=f"Pay {tk(20000)} to Bright Light Wholesale for invoice BLW-5520 (part payment) from the sandbox account",
                       amount=20000, recipient="Bright Light Wholesale", status="pending", origin="agent",
                       request_id=uuid.uuid4().hex[:16], created_at=NOW - timedelta(minutes=3),
                       expires_at=NOW + timedelta(hours=12))
    db.add(pa)
    db.flush()
    aud(NOW - timedelta(minutes=3), "tool_call", "pay_supplier_invoice", 2,
        inputs={"invoice_no": "BLW-5520", "amount": 20000}, result={"status": "pending_confirmation", "pending_action_id": pa.id},
        confirmation="pending", rid=pa.request_id)

    # SMS reminders to customers
    for inv_no, remind_on, status, created_d in (("RE-0001", date(2026, 9, 7), "sent_simulated", date(2026, 9, 6)),
                                                 ("RE-0004", date(2026, 10, 15), "sent_simulated", date(2026, 10, 14)),
                                                 ("RE-0007", date(2026, 10, 20), "scheduled", date(2026, 10, 18)),
                                                 ("RE-0009", date(2026, 10, 21), "scheduled", date(2026, 10, 18))):
        inv = inv_obj[inv_no]
        out = float(inv.amount) - float(inv.amount_paid) if status == "scheduled" else (38380 if inv_no == "RE-0001" else 51450)
        msg = (f"Assalamualaikum. Rana Electric & Hardware: {tk(out)} is due on bill {inv_no}. "
               f"Please pay by bKash 01711-XXXXXX or at the shop. Thank you.")
        db.add(Reminder(business_id=bid, invoice_id=inv.id, counterparty=inv.counterparty, amount=out, remind_on=remind_on,
                        channel="sms", message=msg, status=status, created_at=at(created_d, "10:25" if created_d.day == 6 else "18:35")))
        aud(at(created_d, "10:25" if created_d.day == 6 else "18:35"), "tool_call", "create_payment_reminder", 1,
            inputs={"invoice_no": inv_no, "remind_on": remind_on.isoformat()}, result={"status": status})

    # drafts: follow-ups and letters
    for d, no, tone, lang, subj, body, status in FOLLOWUPS:
        inv = inv_obj[no]
        ts = at(d, "10:22" if d.day == 6 else "18:30")
        db.add(Draft(business_id=bid, kind="invoice_followup", invoice_id=inv.id, recipient=inv.counterparty,
                     language=lang, tone=tone, subject=subj, body=body, status=status, created_at=ts))
        aud(ts, "tool_call", "draft_invoice_followup", 1, inputs={"invoice_no": no, "tone": tone, "language": lang})
    for key, (d, kind, recipient, subj, body) in LETTERS.items():
        ts = at(d, {9: "22:34", 24: "16:36", 7: "11:16", 14: "18:28"}[d.day])
        db.add(Draft(business_id=bid, kind=kind, recipient=recipient, language="en", tone="formal", subject=subj,
                     body=body, status="approved" if key != "rahman_ext" else "draft", created_at=ts))
        aud(ts, "tool_call", "draft_letter", 1, inputs={"kind": kind, "recipient": recipient})
    db.add(Draft(business_id=bid, kind="loan_checklist", recipient=BANK, language="en", tone="",
                 subject="Loan application checklist - SME working capital",
                 body=("Have (bring a copy): trade licence (DSCC), TIN certificate, NID, current account CD-0021-778812.\n"
                       "Can generate here: loan-readiness report (sales, expenses, customer credit, 90-day forecast).\n"
                       "To prepare: 6-month bank statement from the branch; stock list with values; 2 passport photos; "
                       "guarantor's NID and photo; shop rent agreement; last 3 months electricity bills.\n"
                       "Next steps: book a meeting with the SME desk; ask for a written quote with every fee and instalment date; "
                       "check the quote in AI Assistant > Check a loan quote."),
                 status="approved", created_at=at(date(2026, 9, 12), "19:12")))
    aud(at(date(2026, 9, 12), "19:12"), "tool_call", "prepare_loan_checklist", 1, inputs={"amount": 500000})
    db.flush()

    # appointments / custom alerts
    for created_ts, due, title, msg, status in APPOINTMENTS:
        db.add(Alert(business_id=bid, kind="custom", severity="info", title=title, message=msg, due_date=due, status=status,
                     dedupe_key=f"appt:{due.isoformat()}:{title[:40]}", data={"appointment": True}, created_by="user",
                     created_at=created_ts))
        aud(created_ts, "operation", "add_reminder", 1, inputs={"title": title, "due": due.isoformat()})
        if status == "acknowledged":
            aud(at(due, "20:00"), "operation", "alert_acknowledged", 1, inputs={"title": title})
    db.flush()

    # conversations
    def sales_between(lo, hi):
        tot = sum(e["amount"] for e in sim.entries if lo <= e["date"] <= hi)
        tot += sum(r[2] for rows in sim.khata.values() for r in rows if r[3] == "income" and lo <= r[0] <= hi)
        return tot
    for d, hm, turns in chats(sales_between, None):
        ts = at(d, hm)
        conv = Conversation(business_id=bid, user_id=user.id, created_at=ts)
        db.add(conv)
        db.flush()
        for role, text, tools in turns:
            rid = uuid.uuid4().hex[:16]
            db.add(ChatMessage(conversation_id=conv.id, role=role, content=text, created_at=ts,
                               meta={} if role == "user" else {"request_id": rid, "profile": "shared-llm", "tools": tools}))
            if role == "assistant":
                aud(ts, "agent_decision", "answer", inputs={"text": last_user[:500], "language": "en", "profile": "shared-llm"},
                    result={"tools": [f"{t}:ok" for t in tools], "reply": text[:400], "fallback": False}, rid=rid)
            else:
                last_user = text
            ts += timedelta(minutes=rnd.randint(1, 4))
    db.flush()

    # guided tasks through the real pilot service, each on its own historical date
    def guided(kind, day, answers, action=None, hm="21:00", complete=True, reopen=None):
        saved = None
        if reopen is not None:  # replay the past: the invoice was still unpaid that day
            saved = (reopen.status, reopen.amount_paid, reopen.paid_date)
            reopen.status, reopen.amount_paid, reopen.paid_date = "open", 0, None
            db.flush()
        case = GuidedCase(business_id=bid, user_id=user.id, request_key=uuid.uuid4().hex, kind=kind, language="en",
                          status="active", answers={}, created_at=at(day, hm), updated_at=at(day, hm))
        db.add(case)
        db.flush()
        snap = pilot.snapshot(db, bid, day)
        while True:
            pending = [q for q in questions(kind, case.answers, snap) if q["id"] not in case.answers]
            if not pending or pending[0]["id"] not in answers:
                break
            qn = pending[0]
            val = answers[qn["id"]]
            if qn["id"] == "cash" and val is None:  # owner accepts the suggested (recorded) amount
                val = snap["cash"]
            case.answers = {**case.answers, qn["id"]: pilot.validate(qn, val, day)}
        aud(at(day, hm), "operation", "guided_task_started", 1, inputs={"case_id": case.id, "kind": kind})
        if complete:
            preview = pilot.build_preview(db, case, day, action)
            case.preview = preview
            effects = pilot.commit_action(db, case, preview, day)
            case.updated_at = at(day, hm) + timedelta(minutes=9)
            db.flush()
            for model, key in ((Alert, "alert_id"),):
                if key in effects:
                    db.execute(update(model).where(model.id == effects[key]).values(created_at=case.updated_at))
            aud(case.updated_at, "operation", "guided_task_confirmed", 1,
                inputs={"case_id": case.id, "kind": kind, "action": action}, result={k: v for k, v in effects.items()})
        if saved is not None:
            reopen.status, reopen.amount_paid, reopen.paid_date = saved
            db.flush()
        return case

    guided("record", date(2026, 8, 22), {"record_type": "check", "date": "2026-08-22"}, "save", "21:10",
           complete=False)  # abandoned in the middle: shows as an unfinished task
    babul = inv_obj["RE-0001"]
    guided("collect", date(2026, 9, 6), {"invoice_id": str(babul.id), "disputed": "no", "promised_date": "2026-09-14",
                                         "review_date": "2026-09-14"}, "draft", "10:30", reopen=babul)
    guided("loan", date(2026, 9, 10), {
        "lender": "Shakti SME Finance (MFI)", "quote_source": "Field officer visit at the shop, 10 Sep, written quote",
        "principal": 300000, "fees": 9000,
        "schedule": [{"date": (date(2026, 9, 17) + timedelta(weeks=i)).isoformat(), "amount": 3550} for i in range(104)],
        "quote_complete": "yes", "cash": None, "purchase": 250000, "income": 800000, "slow_income": 600000,
        "cash_timing": "daily", "expenses": 560000, "household": 60000, "existing_debt": 0, "other_schedule": [],
        "reserve": 80000, "facts_complete": "yes", "security": "Personal guarantee of wife; no collateral",
        "review_date": "2026-09-25"}, "wait", "22:05")
    guided("stock", date(2026, 9, 15), {
        "product": "Rechargeable emergency light", "quantity": 40, "unit_cost": 650, "delivery": 600, "price": 950,
        "selling_cost": 15, "expected": 30, "evidence": "Load shedding is back; 6 customers asked last week",
        "risk": "Battery faults - supplier gives 7-day replacement", "collection_days": 0, "cash": None,
        "reserve": 80000, "review_date": "2026-10-01"}, "small", "21:12")
    guided("paperwork", date(2026, 9, 27), {
        "topic": "trade", "authority": "dscc", "activity": "Retail and wholesale of electrical goods and hardware",
        "registered": "yes", "period": "FY 2026-27 renewal", "documents": "Old trade licence, NID, rent agreement, holding tax receipt",
        "deadline": "2026-10-31", "deadline_source": "Notice from DSCC Zone 3 tax office pasted at the market",
        "request": "Please guide me on renewing my trade licence for FY 2026-27 and the fees payable."}, "draft", "20:30")
    loan2 = guided("loan", date(2026, 10, 4), {
        "lender": BANK + ", " + BRANCH, "quote_source": "Written offer letter dated 3 Oct 2026, ref NWB/SME/0512",
        "principal": LOAN_AMT, "fees": LOAN_FEE + 900,
        "schedule": [{"date": date(2026 + (10 + i) // 12, (10 + i) % 12 + 1, 6).isoformat(), "amount": EMI} for i in range(24)],
        "quote_complete": "yes", "cash": None, "purchase": 230000, "income": 850000, "slow_income": 680000,
        "cash_timing": "daily", "expenses": 560000, "household": 62000, "existing_debt": 0,
        "other_schedule": [{"date": "2026-10-30", "amount": 71200}], "reserve": 80000, "facts_complete": "yes",
        "security": "Hypothecation of shop stock; personal guarantee of Faruk Ahmed (uncle)", "review_date": "2026-10-20"},
        "save", "20:45")
    m = loan2.result["metrics"]
    reply = (f"I put the offer into Check a loan quote. You would receive {tk(m['net_received'])} after fees and repay "
             f"{tk(m['total_repaid'])} in total, so the loan costs {tk(m['cost'])}. The result is TIGHT: in a usual month your "
             f"lowest balance could fall to {tk(m['usual_minimum'])}, and in a slow month to {tk(m['slow_minimum'])}, against the "
             f"{tk(m['reserve'])} you want to keep. The lowest point comes right after the loan arrives, when you spend "
             f"{tk(230000)} on stock and the month's costs are still ahead. Ways to make it safer: spend less of the loan on stock "
             f"at once, collect Shahjahan Builders' overdue amount first, or ask the bank for a later first instalment. "
             f"This is a check of the numbers you entered, not approval or advice to borrow; it is saved for review.")
    db.execute(update(ChatMessage).where(ChatMessage.content == "__LOAN2__").values(content=reply))
    for e in AUDIT:
        if e["result"].get("reply") == "__LOAN2__":
            e["result"]["reply"] = reply[:400]
    rahman = inv_obj["RCT-0917"]
    guided("shortfall", date(2026, 10, 9), {
        "purpose": "Rahman Cable Traders bill RCT-0917 balance", "amount": 71200, "due_date": "2026-10-30", "cash": None,
        "essentials": 60000, "collections": 113000, "existing_debt": 0, "reserve": 80000, "review_date": "2026-10-25"},
        "supplier", "21:30")
    kamal = inv_obj["RE-0005"]
    guided("collect", date(2026, 10, 16), {"invoice_id": str(kamal.id), "disputed": "yes", "promised_date": "2026-10-25",
                                           "review_date": "2026-10-23"}, "draft", "18:50")
    guided("stock", date(2026, 10, 18), {"product": "Room heater 2000W (second batch)", "quantity": 20, "unit_cost": 1650},
           None, "22:30", complete=False)
    # pilot snapshot needs cash; fill the "cash" answers the owner would have accepted (suggested value)
    db.flush()

    # loan-readiness reports (real PDFs from his books as of that day)
    from sme_copilot.agent.toolkit import ToolContext
    from sme_copilot.agent.tools_actions import ReportArgs, generate_loan_report
    for d, amount, purpose in ((date(2026, 9, 12), 500000, "inventory"),
                               (date(2026, 9, 23), 400000, "seasonal")):
        try:
            ctx = ToolContext(session=db, business=b, user=user, as_of=d, request_id=uuid.uuid4().hex[:16], origin="api")
            res = generate_loan_report(ctx, ReportArgs(amount=amount, purpose=purpose))
            db.execute(update(Report).where(Report.id == res.report_id).values(created_at=at(d, "19:15")))
            aud(at(d, "19:15"), "tool_call", "generate_loan_report", 1, inputs={"amount": amount, "purpose": purpose},
                result={"report_id": res.report_id, "readiness_score": res.readiness_score})
        except Exception as exc:  # report the failure, keep seeding
            print(f"loan report {d}: FAILED {type(exc).__name__}: {exc}")

    # logins on the days he used the app
    used = sorted({e["ts"].date() for e in sim.entries} | {a["ts"].date() for a in AUDIT})
    for d in used:
        first = min([a["ts"] for a in AUDIT if a["ts"].date() == d] + [datetime.combine(d, datetime.max.time())])
        if d == START:
            continue
        aud(first - timedelta(minutes=2), "auth", "login", inputs={"ip": IP if rnd.random() < .7 else "103.92.84.17"})
    aud(at(date(2026, 9, 3), "08:10"), "auth", "login_failed", inputs={"ip": "103.92.84.17", "username": USER})

    # system alerts as they are today (overdue invoices, low stock, cash, payments due)
    db.flush()
    from sme_copilot.forecasting.alerts import refresh_alerts
    try:
        made = refresh_alerts(db, b, TODAY)
        print(f"refresh_alerts: {len(made)} alerts")
    except Exception as exc:
        print(f"refresh_alerts FAILED {type(exc).__name__}: {exc}")

    write_audit(db, bid)
    db.commit()

    # ---- summary
    from sme_copilot.security.audit import verify_chain
    from sme_copilot.tools.stock import stock_rows
    print("imports:")
    for k, v in import_reports.items():
        print(f"  {k}: {v}")
    snap = pilot.snapshot(db, bid, TODAY)
    print(f"cash today (books): {tk(snap['cash'])}  records: {snap['record_count']}")
    print("stock:")
    for r in stock_rows(db, bid, TODAY):
        print(f"  {r['name']:<38} qty {r['qty']:>6}  sold30 {r['sold_30d']:>6}  days {r['days_left']}  {r['status']}")
    print("audit:", verify_chain(db))
    counts = {m.__tablename__: db.query(m).count() for m in (Transaction, Invoice, Draft, Alert, Reminder, ChatMessage,
                                                             Conversation, GuidedCase, Report, AuditEvent, StockMovement)}
    print("rows:", counts)
    db.close()


if __name__ == "__main__":
    main()
