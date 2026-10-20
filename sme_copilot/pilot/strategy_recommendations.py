"""Record-grounded planning opportunities; no invented quotes or automatic purchases.

One quantity source per item avoids counting a stock movement, its cash entry and
its invoice as three sales. Linked movements use the business date, not upload time.
"""
from collections import Counter, OrderedDict, defaultdict
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import re
import statistics
import calendar

from sqlalchemy import select

from sme_copilot.models import Item, StockMovement, Transaction, Invoice, InvoiceLine, InvoicePayment
from sme_copilot.tools.textnorm import normalize

_rankings = OrderedDict()


def text(en, bn, zh):
    return {"en": en, "bn": bn, "zh": zh}


def load_history(db, business, today):
    bid = business.id
    items = list(db.scalars(select(Item).where(Item.business_id == bid).order_by(Item.id)))
    all_tx = list(db.scalars(select(Transaction).where(Transaction.business_id == bid).order_by(Transaction.id)))
    valid = {t.id: t for t in all_tx if t.txn_date <= today and not t.is_duplicate}
    moves = list(db.scalars(select(StockMovement).join(Item).where(Item.business_id == bid).order_by(StockMovement.id)))
    invoices = list(db.scalars(select(Invoice).where(Invoice.business_id == bid, Invoice.issue_date <= today).order_by(Invoice.id)))
    lines = list(db.execute(select(InvoiceLine, Invoice).join(Invoice).where(Invoice.business_id == bid, Invoice.issue_date <= today).order_by(InvoiceLine.id)))
    payment_ids = set(db.scalars(select(InvoicePayment.transaction_id).where(InvoicePayment.business_id == bid)))
    raw = [today, business.name, business.sector, business.district, business.prefs, business.opening_cash_balance, business.opening_balance_date,
           [(i.id, i.name, i.unit, i.aliases, i.opening_qty, i.reorder_level) for i in items],
           [(t.id, t.txn_date, t.item, t.quantity, t.amount, t.category, t.direction, t.is_duplicate) for t in all_tx],
           [(m.id, m.item_id, m.qty_change, m.reason, m.transaction_id, m.created_at) for m in moves],
           [(i.id, i.status, i.kind, i.issue_date, i.due_date, i.amount, i.amount_paid) for i in invoices],
           [(l.id, l.invoice_id, l.description, l.quantity, l.rate) for l, _ in lines], sorted(x for x in payment_ids if x is not None)]
    stamp = hashlib.sha256(json.dumps(raw, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    names = defaultdict(set)
    for i in items:
        for name in [i.name, *(i.aliases or [])]:
            names[normalize(name)].add(i.id)
    def match(name):
        ids = names.get(normalize(name or ""), set())
        return next(iter(ids)) if len(ids) == 1 else None
    events = defaultdict(list)
    on_hand = {i.id: float(i.opening_qty) for i in items}
    for m in moves:
        if m.transaction_id is not None:
            t = valid.get(m.transaction_id)
            if not t:  # deleted, duplicate, future or cross-business transaction
                continue
            when = t.txn_date
        else:
            when = m.created_at.date()
            if when > today:
                continue
        on_hand[m.item_id] += m.qty_change
        reason = m.reason.removeprefix("reversal:")
        if m.transaction_id is not None:
            expected = {("in", "sales"): "sale", ("out", "sales_returns"): "sale_return",
                        ("out", "inventory"): "purchase", ("out", "stock_purchase"): "purchase",
                        ("in", "purchase_returns"): "purchase_return"}.get((t.direction, t.category))
            if reason != expected:
                continue
        if reason in ("sale", "sale_return", "purchase", "purchase_return"):
            kind = "sale" if reason in ("sale", "sale_return") else "purchase"
            qty = -m.qty_change if kind == "sale" else m.qty_change
            events[m.item_id].append((when, kind, qty, "stock", m.id))
    # A linked cash entry does not add a second quantity event for the same item.
    movement_items = {key for key, rows in events.items() if rows}
    for t in valid.values():
        key = match(t.item)
        if not key or key in movement_items or t.quantity is None or t.quantity <= 0 or t.id in payment_ids:
            continue
        kind = {("in", "sales"): "sale", ("out", "sales_returns"): "sale_return",
                ("out", "inventory"): "purchase", ("out", "stock_purchase"): "purchase",
                ("in", "purchase_returns"): "purchase_return"}.get((t.direction, t.category))
        if kind:
            events[key].append((t.txn_date, "sale" if kind.startswith("sale") else "purchase",
                                -t.quantity if kind.endswith("return") else t.quantity, "transaction", t.id))
    recorded_items = {key for key, rows in events.items() if rows}
    for line, inv in lines:
        key = match(line.description)
        if not key or key in recorded_items or inv.status in ("draft", "written_off"):
            continue
        events[key].append((inv.issue_date, "sale" if inv.kind == "receivable" else "purchase", line.quantity, "invoice", inv.id))
    cash = Decimal(str(business.opening_cash_balance)) + sum(
        (Decimal(str(t.amount)) * (1 if t.direction == "in" else -1) for t in valid.values()
         if business.opening_balance_date is None or t.txn_date > business.opening_balance_date), Decimal(0))
    bills = sum((Decimal(str(max(0, i.amount - i.amount_paid))) for i in invoices
                 if i.kind == "payable" and i.status not in ("draft", "paid", "written_off") and i.due_date <= today + timedelta(days=30)), Decimal(0))
    return {"stamp": stamp, "items": items, "events": events, "on_hand": on_hand,
            "movement_items": movement_items, "transactions": valid, "cash": cash, "bills": bills}


def candidates(db, business, today):
    h = load_history(db, business, today)
    result = []
    since, prior = today - timedelta(days=29), today - timedelta(days=59)
    start90 = today - timedelta(days=89)
    def add(key, signal, kind, title, reason, checks, *, item=None, priority=40, evidence=None, basis="records", href=None):
        trace = sorted(h["events"].get(item.id, []) if item else [], key=lambda r: r[0], reverse=True)[:6]
        source = trace[0][3] if trace else None
        result.append({"id": key, "signal": signal, "kind": kind, "title": title, "reason": reason,
                       "checks": checks, "item": item.name if item else None, "unit": item.unit if item else None,
                       "evidence": evidence or [], "basis": basis, "priority": priority, "href": href,
                       "records_href": "#stock" if source == "stock" else "#invoices" if source == "invoice" or item is None else "#data?tools=all",
                       "supporting_records": [{"date": r[0].isoformat(), "kind": r[1], "quantity": r[2], "source": r[3], "id": r[4]} for r in trace],
                       "as_of": today.isoformat(), "stamp": h["stamp"]})
    common = text("Check the quote, storage costs, bill money and current rules before buying.",
                  "কেনার আগে দাম, সংরক্ষণ খরচ, বিলের টাকা ও বর্তমান নিয়ম যাচাই করুন।",
                  "购买前核实报价、储存成本、账单资金及现行规定。")
    if business.opening_balance_date and business.opening_balance_date <= today and h["bills"] > 0 and h["cash"] < h["bills"]:
        add("protect-cash", "cash", "bulk", text("Keep bill money safe before buying more", "আরও কেনার আগে বিলের টাকা রাখুন", "增加采购前先保留账单资金"),
            text("Your recorded money is below the unpaid supplier bills due within 30 days.", "৩০ দিনের মধ্যে দেওয়ার বাকি সরবরাহকারী বিলের তুলনায় হিসাবের টাকা কম।", "记录的资金少于30天内到期的未付供应商账单。"),
            text("Review bills and realistic collections first. This does not include every business or household commitment.", "আগে বিল ও আদায়যোগ্য পাওনা দেখুন। সব ব্যবসা ও সংসার খরচ এখানে ধরা হয়নি।", "先核对账单和实际可收回的款项。这里未包含所有经营及家庭支出。"), priority=0, href="#money?tab=ahead",
            evidence=[{"label": text("Recorded money", "হিসাবের টাকা", "记录资金"), "value": float(h["cash"]), "currency": "BDT"},
                      {"label": text("Supplier bills due within 30 days", "৩০ দিনের মধ্যে সরবরাহকারীকে দিতে হবে", "30天内到期的供应商账单"), "value": float(h["bills"]), "currency": "BDT"}])
    growth = []
    for item in h["items"]:
        rows = h["events"].get(item.id, [])
        sales = [r for r in rows if r[1] == "sale"]
        sale_totals = Counter(); purchase_totals = Counter()
        for r in rows:
            (sale_totals if r[1] == "sale" else purchase_totals)[r[0]] += r[2]
        recent = max(0, sum(r[2] for r in sales if since <= r[0] <= today))
        previous = max(0, sum(r[2] for r in sales if prior <= r[0] < since))
        sale_days = sum(1 for d, n in sale_totals.items() if since <= d <= today and n > 0)
        old_days = sum(1 for d, n in sale_totals.items() if prior <= d < since and n > 0)
        purchase_days = sum(1 for d, n in purchase_totals.items() if start90 <= d <= today and n > 0)
        stock_known = item.id in h["movement_items"]
        qty = round(h["on_hand"][item.id], 3) if stock_known else None
        evidence = [{"label": text("Recorded units sold: last 30 days", "শেষ ৩০ দিনে হিসাবের বিক্রি", "最近30天的记录销售数量"), "value": round(recent, 3), "unit": item.unit},
                    {"label": text("Period", "সময়কাল", "期间"), "value": f"{since.isoformat()} – {today.isoformat()}"}]
        if qty is not None:
            evidence.insert(0, {"label": text("Recorded stock", "হিসাবের মজুত", "记录库存"), "value": qty, "unit": item.unit})
        if stock_known and recent > 0 and (qty <= item.reorder_level or qty <= recent / 30 * 7):
            add(f"restock-{item.id}", "restock", "bulk", text(f"Review a purchase of {item.name}", f"{item.name} কেনার পরিকল্পনা দেখুন", f"考虑补购 {item.name}"),
                text("Recorded stock is low compared with recent sales or your stock threshold.", "সাম্প্রতিক বিক্রি বা আপনার নির্ধারিত সীমার তুলনায় হিসাবের মজুত কম।", "与近期销售或您设定的库存门槛相比，记录库存偏低。"), common,
                item=item, priority=19 if qty <= 0 else 20, evidence=evidence)
        elif stock_known and qty > 0 and recent > 0 and qty > recent * 3 and sale_days >= 4:
            add(f"wait-{item.id}", "overstock", "bulk", text(f"Use existing {item.name} before buying more", f"আরও কেনার আগে থাকা {item.name} ব্যবহার করুন", f"增加采购前先使用现有 {item.name}"),
                text("Recorded stock exceeds three times the units sold in the last 30 days.", "শেষ ৩০ দিনে বিক্রি হওয়া এককের তিন গুণের বেশি মজুত হিসাবে আছে।", "记录库存超过最近30天销售数量的三倍。"),
                text("Check unsold stock and expiry first. Recent sales are not a guarantee of future demand.", "আগে অবিক্রীত পণ্য ও মেয়াদ দেখুন। সাম্প্রতিক বিক্রি ভবিষ্যৎ চাহিদার নিশ্চয়তা নয়।", "先检查积压和保质期。近期销售不能保证未来需求。"),
                item=item, priority=10, evidence=evidence)
        elif purchase_days >= 3:
            add(f"bulk-{item.id}", "bulk", "bulk", text(f"Compare a larger order of {item.name}", f"{item.name}-এর বড় অর্ডার তুলনা করুন", f"比较 {item.name} 的较大订单"),
                text(f"You recorded purchases on {purchase_days} different days in the last 90 days.", f"শেষ ৯০ দিনে {purchase_days}টি আলাদা দিনে কেনার হিসাব আছে।", f"最近90天内记录了{purchase_days}个不同采购日。"),
                common, item=item, priority=40, evidence=[{"label": text("Purchase days in 90 days", "৯০ দিনে কেনার দিন", "90天内采购天数"), "value": purchase_days}, *evidence])
        if previous > 0 and recent >= previous * 1.2 and min(sale_days, old_days) >= 6:
            growth.append((recent / previous, item, recent, previous))
        # Two completed, reasonably covered years are needed to label a recorded busy month.
        by_year = defaultdict(lambda: defaultdict(float)); dates = defaultdict(set)
        for when, amount in sale_totals.items():
            if when.year in (today.year - 2, today.year - 1):
                by_year[when.year][when.month] += amount
                if amount > 0: dates[(when.year, when.month)].add(when)
        peaks = []
        for year in (today.year - 2, today.year - 1):
            values = by_year[year]
            positive = [v for v in values.values() if v > 0]
            if len(positive) >= 6:
                month = max(values, key=values.get)
                if values[month] >= statistics.median(positive) * 1.5 and len(dates[(year, month)]) >= 3:
                    peaks.append(month)
        if len(peaks) == 2 and peaks[0] == peaks[1]:
            month = peaks[0]
            month_bn = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"][month - 1]
            add(f"seasonal-{item.id}", "seasonal", "seasonal", text(f"Plan ahead for {item.name}'s busy period", f"{item.name}-এর ব্যস্ত সময়ের আগে পরিকল্পনা করুন", f"提前规划 {item.name} 的旺季"),
                text(f"{calendar.month_name[month]} had the highest recorded sales in {today.year - 2} and {today.year - 1}.", f"{today.year - 2} ও {today.year - 1} সালে {month_bn} মাসে হিসাবে সর্বোচ্চ বিক্রি ছিল।", f"在{today.year - 2}和{today.year - 1}年中，{month}月的记录销售量均最高。"),
                common, item=item, priority=35,
                evidence=[{"label": text(f"{calendar.month_name[month]} {year}", f"{month_bn} {year}", f"{year}年{month}月"),
                           "value": by_year[year][month], "unit": item.unit} for year in (today.year - 2, today.year - 1)])
    if growth:
        _, item, recent, previous = max(growth, key=lambda x: x[0])
        add(f"equipment-{item.id}", "equipment", "equipment", text("Check whether extra equipment would help", "বাড়তি যন্ত্র কাজে লাগবে কি না দেখুন", "检查增加设备是否有帮助"),
            text(f"Recorded sales of {item.name} grew across two 30-day periods.", f"পরপর দুই ৩০ দিনের সময়ে {item.name}-এর হিসাবের বিক্রি বেড়েছে।", f"{item.name} 的记录销售量在两个连续30天期间有所增长。"),
            text("Confirm missed orders or a capacity limit, then compare buying, renting and waiting. Sales growth alone does not show that you need a machine.", "অর্ডার ফেরত বা ধারণক্ষমতার সীমা যাচাই করে কেনা, ভাড়া ও অপেক্ষা তুলনা করুন। শুধু বিক্রি বাড়লেই যন্ত্র লাগবে এমন নয়।", "先确认未能满足的订单或容量限制，再比较购买、租赁和等待。销售增长本身不能证明需要新设备。"),
            item=item, priority=50, evidence=[{"label": text("Recent 30 days", "সাম্প্রতিক ৩০ দিন", "最近30天"), "value": recent, "unit": item.unit},
                                   {"label": text("Previous 30 days", "আগের ৩০ দিন", "之前30天"), "value": previous, "unit": item.unit}])
    context = f"{business.name} {business.sector} {(business.prefs or {}).get('about', '')}"
    juice = bool(re.search(r"juice|জুস|শরবত", context, re.I))
    if juice and not any(x["signal"] == "seasonal" for x in result):
        add("seasonal-fruit", "seasonal", "seasonal", text("Plan fruit availability beyond the season", "মৌসুমের পরেও ফল রাখার পরিকল্পনা করুন", "规划季节之后的水果供应"),
            text("A seasonal storage plan may be useful for a juice business.", "জুসের ব্যবসায় মৌসুমি সংরক্ষণের পরিকল্পনা কাজে লাগতে পারে।", "果汁业务可以考虑季节性储存计划。"),
            text("Confirm which fruit you sell, safe preparation and storage life, freezer and power costs, cash needs and current storage rules. A freezer does not establish safe shelf life.", "কোন ফল বিক্রি করেন, নিরাপদ প্রস্তুতি ও সংরক্ষণকাল, ফ্রিজার ও বিদ্যুৎ খরচ, টাকার প্রয়োজন ও মজুতের নিয়ম যাচাই করুন। শুধু ফ্রিজার থাকলেই নিরাপদ মেয়াদ ঠিক হয় না।", "核实销售的水果、安全处理及储存期限、冰柜及电力成本、资金需求和现行储存规定。有冰柜并不能确定安全储存期限。"),
            priority=60, basis="business_type")
    if not result:
        add("start-records", "baseline", "bulk", text("Build a buying plan from your sales", "বিক্রির হিসাব থেকে কেনার পরিকল্পনা করুন", "根据销售记录制定采购计划"),
            text("There is not enough dated item history for a specific purchasing or investment suggestion yet.", "নির্দিষ্ট কেনা বা বিনিয়োগের পরামর্শের জন্য তারিখসহ পণ্যের যথেষ্ট হিসাব এখনও নেই।", "目前缺少足够的商品日期记录，无法给出具体采购或投资建议。"),
            text("Record items sold and bought, with quantities. You can still explore a plan below.", "পরিমাণসহ পণ্য কেনা ও বিক্রি লিখুন। নিচে চাইলে পরিকল্পনা শুরু করতে পারবেন।", "记录买卖商品及数量。您仍可使用下方工具探索计划。"),
            priority=90, basis="missing_history", href="#data")
    return h, sorted(result, key=lambda x: (x["priority"], x["id"]))


def recommendations(db, business, today):
    from .question_model import select_id
    h, rows = candidates(db, business, today)
    # Preserve cash/overstock/restock priority. AI may rank only discretionary opportunities.
    eligible = [r["id"] for r in rows if 30 <= r["priority"] < 60][:8]
    key = (business.id, h["stamp"])
    if key not in _rankings:
        chosen = select_id({"purpose": "strategy_suggestions", "business_category": "juice" if any(r["id"] == "seasonal-fruit" for r in rows) else "other",
                            "opportunities": [{"id": r["id"], "signal": r["signal"], "evidence": [{"value": e["value"]} for e in r["evidence"] if isinstance(e["value"], (int, float))]}
                                              for r in rows if r["id"] in eligible]}, eligible) if len(eligible) > 1 else None
        _rankings[key] = chosen
        if len(_rankings) > 128: _rankings.popitem(last=False)
    chosen = _rankings[key]
    if chosen in eligible:
        rows.sort(key=lambda r: (r["priority"] if r["priority"] < 30 else 30 if r["id"] == chosen else r["priority"], r["id"]))
    selected, seen = [], set()
    for row in rows:
        if row["signal"] not in seen:
            selected.append(row); seen.add(row["signal"])
        if len(selected) == 3: break
    return {"suggestions": selected, "as_of": today.isoformat(), "ranking_source": "model" if chosen in eligible else "rules"}


def find_suggestion(db, business, today, suggestion_id):
    _, rows = candidates(db, business, today)
    return next((r for r in rows if r["id"] == suggestion_id and not r["href"]), None)
