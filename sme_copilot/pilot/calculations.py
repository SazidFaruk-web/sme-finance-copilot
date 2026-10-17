"""Full-schedule cash scenarios, never a lender approval or an invented quote."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import ceil


def money(v):
    return float(Decimal(str(v)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP))


def loan(a, today):
    required = ("principal", "fees", "schedule", "cash", "purchase", "income", "slow_income", "expenses",
                "household", "existing_debt", "other_schedule", "reserve", "security", "cash_timing", "lender", "quote_source")
    missing = [k for k in required if a.get(k) is None or a.get(k) == ""]
    if not a.get("schedule"):
        missing.append("schedule")
    if a.get("quote_complete") != "yes" or a.get("facts_complete") != "yes":
        missing.append("confirmation")
    if a.get("cash_timing") == "uneven" and not a.get("income_schedule"):
        missing.append("income_schedule")
    if missing:
        return {"status": "need_information", "missing": sorted(set(missing)), "metrics": {}}
    schedule = sorted(a["schedule"], key=lambda p: p["date"])
    end = date.fromisoformat(schedule[-1]["date"])
    if end < today or any(date.fromisoformat(p["date"]) < today for p in schedule):
        return {"status": "need_information", "missing": ["future_schedule"], "metrics": {}}
    net = money(a["principal"] - a["fees"])
    initial = money(a["cash"] + net - a["purchase"])
    repayments = {}
    for p in schedule + a["other_schedule"]:
        repayments[p["date"]] = repayments.get(p["date"], Decimal(0)) + Decimal(str(p["amount"]))
    totals = money(sum(p["amount"] for p in schedule))
    def scenario(receipts, delay=0):
        balance = Decimal(str(initial)); minimum = balance; lowest_on = today.isoformat()
        expenses = sum(Decimal(str(a[k])) for k in ("expenses", "household", "existing_debt"))
        # Hold each month's essentials (including weekly debt) at the start of the
        # month-period. This avoids falsely smoothing a payment away before it is due.
        daily_receipts = Decimal(str(receipts)) / Decimal("30.4375")
        dated_receipts = {}
        for p in a.get("income_schedule") or []:
            when = (date.fromisoformat(p["date"]) + timedelta(days=delay)).isoformat()
            factor = Decimal(str(receipts)) / Decimal(str(a["income"])) if a["income"] else Decimal(0)
            dated_receipts[when] = dated_receipts.get(when, Decimal(0)) + Decimal(str(p["amount"])) * factor
        series = []
        day = today
        while day <= end:
            elapsed = (day - today).days
            if elapsed % 30 == 0:
                balance -= expenses
            if a["cash_timing"] == "uneven":
                balance += dated_receipts.get(day.isoformat(), Decimal(0))
            elif elapsed > delay:
                balance += daily_receipts
            balance -= repayments.get(day.isoformat(), Decimal(0))
            if balance < minimum:
                minimum, lowest_on = balance, day.isoformat()
            if day.isoformat() in repayments or day == end:
                series.append({"date": day.isoformat(), "balance": money(balance)})
            day += timedelta(days=1)
        return {"minimum": money(minimum), "minimum_date": lowest_on, "end": money(balance), "series": series}
    usual, slow = scenario(a["income"]), scenario(a["slow_income"], delay=7)
    status = "manageable" if min(usual["minimum"], slow["minimum"]) >= a["reserve"] and net > 0 else "tight"
    # A repayment quote smaller than principal may omit a balloon or charges.
    if totals < a["principal"] or a["slow_income"] > a["income"]:
        status = "need_information"
    return {"status": status, "metrics": {"net_received": net, "total_repaid": totals,
        "cost": money(totals + a["fees"] - a["principal"]), "usual_minimum": usual["minimum"],
        "slow_minimum": slow["minimum"], "reserve": a["reserve"]},
        "usual": usual, "slow": slow, "schedule": schedule, "end_date": end.isoformat(),
        "assumption": "monthly_costs_reserved_upfront_slow_receipts_delayed_7_days", "eligibility": "not_assessed",
        "source": {"kind": "owner_quote", "lender": a["lender"], "reference": a["quote_source"]}}


def stock(a):
    keys = ("quantity", "unit_cost", "delivery", "price", "selling_cost", "expected", "cash", "reserve", "collection_days")
    if any(a.get(k) is None for k in keys) or not a.get("evidence") or not a.get("risk"):
        return {"status": "need_information", "metrics": {}}
    quantity = a["quantity"]
    contribution = a["price"] - a["unit_cost"] - a["selling_cost"]
    investment = quantity * a["unit_cost"] + a["delivery"]
    expected = min(quantity, a["expected"])
    slow = expected // 2
    return {"status": "test_small" if contribution > 0 and a["cash"] - investment >= a["reserve"] else "wait",
        "metrics": {"needed_now": money(investment), "cash_left": money(a["cash"] - investment),
            "per_item": money(contribution), "break_even_units": ceil(a["delivery"] / contribution) if contribution > 0 else None,
            "expected_contribution": money(expected * contribution - a["delivery"]),
            "slow_contribution": money(slow * contribution - a["delivery"]), "unsold_items": quantity - slow,
            "collection_days": a["collection_days"]}, "assumption": "half_expected_sales_no_unsold_stock_income"}
