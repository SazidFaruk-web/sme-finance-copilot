from datetime import date

import pytest

from sme_copilot.tools.categorize import categorize, detect_direction
from sme_copilot.tools.nl_entry import parse_date_any, parse_entry

T = date(2026, 10, 14)


@pytest.mark.parametrize("text,amount,direction,category,channel", [
    ("sold 12 shirts for 6000 taka cash", 6000, "in", "sales", "cash"),
    ("paid shop rent 15000", 15000, "out", "rent", "cash"),
    ("১২টা শার্ট বিক্রি করলাম ৬০০০ টাকায়", 6000, "in", "sales", "cash"),
    ("dokan bhara 15k dilam bkash e", 15000, "out", "rent", "bkash"),
    ("received 25,000 from Karim Traders via bank", 25000, "in", "sales", "bank"),
    ("bought 500 pcs buttons 2,500 tk", 2500, "out", "inventory", "cash"),
    ("beton dilam 3 jon staff ke 36000", 36000, "out", "salary", "cash"),
    ("electricity bill 4200 paid nagad", 4200, "out", "utilities", "nagad"),
    ("gotokal 2.5 lakh er mal kinlam", 250000, "out", "inventory", "cash"),
    ("kisti dilam 12500", 12500, "out", "loan_repayment", "cash"),
    ("বিদ্যুৎ বিল ৩২০০ টাকা দিলাম", 3200, "out", "utilities", "cash"),
    ("gari bhara 800", 800, "out", "transport", "cash"),
])
def test_parse_entry_multilingual(text, amount, direction, category, channel):
    e = parse_entry(text, T)
    assert (e.amount, e.direction, e.category, e.channel) == (amount, direction, category, channel)
    assert e.confidence >= 0.7 and not e.missing


def test_quantity_item_counterparty_and_dates():
    e = parse_entry("sold 12 shirts for 6000 taka cash", T)
    assert e.quantity == 12 and e.item == "shirts"
    e = parse_entry("received 25,000 from Karim Traders via bank yesterday", T)
    assert e.counterparty == "Karim Traders" and e.txn_date == "2026-10-13"
    assert parse_entry("got 8000 from customer on 10/10/2026", T).txn_date == "2026-10-10"
    assert parse_entry("sold goods 5000 on 3 oct", T).txn_date == "2026-10-03"


def test_incomplete_entry_reports_missing():
    e = parse_entry("hello there", T)
    assert e.amount is None and "amount" in e.missing and "direction" in e.missing


def test_longest_keyword_wins():
    assert categorize("dokan bhara").category == "rent"
    assert categorize("gari bhara").category == "transport"
    assert categorize("wholesale purchase of zippers").category == "inventory"  # not "sale"


def test_direction_respected_in_categorize():
    assert categorize("rent", "in").category == "sales"  # an inflow can't be rent paid
    assert detect_direction("paid something")[0] == "out"
    assert detect_direction("taka pelam")[0] == "in"


@pytest.mark.parametrize("raw,expected", [
    ("14/10/2026", date(2026, 10, 14)), ("2026-10-14", date(2026, 10, 14)), ("14-Oct-2026", date(2026, 10, 14)),
    ("১৪/১০/২০২৬", date(2026, 10, 14)), ("14/10/2026 10:30", date(2026, 10, 14)), ("", None), ("garbage", None),
])
def test_parse_date_any(raw, expected):
    assert parse_date_any(raw) == expected


@pytest.mark.parametrize("text,amount,direction,category", [
    ("kastomar cover ferot dilo 200", 200, "out", "sales_returns"),
    ("customer return 500", 500, "out", "sales_returns"),
    ("ferot dilam 300", 300, "out", "sales_returns"),
    ("ফেরত দিলাম ২০০", 200, "out", "sales_returns"),
    ("ফেরত দিয়েছি ২০০", 200, "out", "sales_returns"),
    ("ferot pelam 400", 400, "in", "other_income"),        # money received back, not a customer return
    ("ফেরত পেলাম ৪০০", 400, "in", "other_income"),
    ("loan ferot dilam 5000", 5000, "out", "loan_repayment"),
    ("return to supplier 900", 900, "in", "purchase_returns"),
])
def test_returns_and_refunds(text, amount, direction, category):
    e = parse_entry(text, T)
    assert (e.amount, e.direction, e.category) == (amount, direction, category)
