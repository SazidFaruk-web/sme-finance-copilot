"""Finance analysis tools vs hand-computed ground truth."""
from datetime import date

import pandas as pd
import pytest

from sme_copilot.tools.analysis import (
    aging,
    break_even,
    business_metrics,
    explain_change,
    income_expense_summary,
    payment_behavior,
    previous_period,
    profitability,
    resolve_period,
    seasonality,
    top_cost_drivers,
)
from tests.conftest import make_txn_df

AS_OF = date(2026, 10, 14)


def three_months():
    """Jul-Sep 2026, identical months:
    sales 300k | inventory 150k (COGS) | rent 30k + salary 45k (fixed) | transport 15k (variable)
    loan repayment 20k (financing) | owner drawings 10k (non-operating)"""
    rows, i = [], 0
    for m in (7, 8, 9):
        for amt, d, cat in [(300_000, "in", "sales"), (150_000, "out", "inventory"), (30_000, "out", "rent"),
                            (45_000, "out", "salary"), (15_000, "out", "transport"),
                            (20_000, "out", "loan_repayment"), (10_000, "out", "owner_drawings")]:
            i += 1
            rows.append((i, f"2026-{m:02d}-10", amt, d, cat, "Karim Knit" if cat == "sales" else ""))
    return make_txn_df(rows)


def test_resolve_period_variants():
    assert resolve_period("last_3_months", AS_OF)[:2] == (date(2026, 7, 1), date(2026, 9, 30))
    assert resolve_period("this_month", AS_OF)[:2] == (date(2026, 10, 1), AS_OF)
    assert resolve_period("last_month", AS_OF)[:2] == (date(2026, 9, 1), date(2026, 9, 30))
    assert resolve_period("last_30_days", AS_OF)[:2] == (date(2026, 9, 15), AS_OF)
    assert resolve_period("fiscal_ytd", AS_OF)[0] == date(2026, 7, 1)
    assert resolve_period("2026-02", AS_OF)[:2] == (date(2026, 2, 1), date(2026, 2, 28))
    with pytest.raises(ValueError):
        resolve_period("someday", AS_OF)
    assert previous_period(date(2026, 7, 1), date(2026, 9, 30)) == (date(2026, 4, 1), date(2026, 6, 30))
    assert previous_period(date(2026, 9, 15), date(2026, 10, 14)) == (date(2026, 8, 16), date(2026, 9, 14))


def test_summary_totals_and_trace():
    df = three_months()
    r = income_expense_summary(df, date(2026, 7, 1), date(2026, 9, 30))
    assert r.total_income == 900_000
    assert r.total_expense == 810_000
    assert r.net_cash_flow == 90_000
    assert r.expense_by_category[0].category == "inventory" and r.expense_by_category[0].share_pct == pytest.approx(55.6, abs=0.1)
    assert len(r.monthly) == 3 and r.monthly[0].net == 30_000
    assert r.trace.row_count == 21 and r.trace.steps[-1].expression == "900,000 - 810,000"


def test_profitability_margins():
    r = profitability(three_months(), date(2026, 7, 1), date(2026, 9, 30))
    assert r.revenue == 900_000 and r.cogs == 450_000
    assert r.gross_profit == 450_000 and r.gross_margin_pct == 50.0
    assert r.fixed_opex == 225_000 and r.variable_opex == 45_000
    assert r.operating_profit == 180_000 and r.net_margin_pct == 20.0
    assert r.excluded["loan_repayments_and_financing_out"] == 60_000
    assert r.excluded["owner_drawings_and_transfers"] == 30_000
    assert r.trace.row_count == 15  # sales + inventory + rent + salary + transport rows only


def test_break_even():
    r = break_even(three_months(), AS_OF, months=3)
    assert r.avg_monthly_fixed_costs == 75_000
    assert r.variable_cost_ratio == pytest.approx(0.55)
    assert r.break_even_monthly_revenue == pytest.approx(166_666.67, abs=0.01)
    assert r.margin_of_safety_pct == pytest.approx(44.44, abs=0.01)
    assert r.status == "above_break_even"


def test_break_even_no_revenue_and_negative_contribution():
    assert break_even(make_txn_df([(1, "2026-09-01", 5000, "out", "rent")]), AS_OF).status == "no_revenue"
    df = make_txn_df([(1, "2026-09-01", 1000, "in", "sales"), (2, "2026-09-02", 2000, "out", "inventory")])
    assert break_even(df, AS_OF).status == "variable_costs_exceed_revenue"


def invoices_df():
    recs = [
        (1, "receivable", "INV-1", "Alpha", 50_000, 0, "2026-10-01", "2026-10-20", None, "open"),
        (2, "receivable", "INV-2", "Beta", 100_000, 20_000, "2026-09-01", "2026-09-30", None, "partial"),
        (3, "receivable", "INV-3", "Alpha", 60_000, 0, "2026-06-01", "2026-07-01", None, "open"),
        (4, "receivable", "INV-4", "Beta", 70_000, 70_000, "2026-05-01", "2026-05-31", "2026-06-15", "paid"),
        (5, "payable", "P-1", "Supplier X", 40_000, 0, "2026-08-01", "2026-08-20", None, "open"),
    ]
    df = pd.DataFrame(recs, columns=["id", "kind", "invoice_no", "counterparty", "amount", "amount_paid",
                                     "issue_date", "due_date", "paid_date", "status"])
    for c in ("issue_date", "due_date", "paid_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def test_receivable_aging_buckets():
    r = aging(invoices_df(), AS_OF, "receivable")
    assert r.buckets == {"not_due": 50_000, "1-30": 80_000, "31-60": 0, "61-90": 0, "90+": 60_000}
    assert r.total_outstanding == 190_000 and r.overdue_total == 140_000 and r.overdue_count == 2
    assert r.items[0].invoice_no == "INV-3" and r.items[0].days_past_due == 105
    alpha = next(c for c in r.by_counterparty if c["counterparty"] == "Alpha")
    assert alpha["outstanding"] == 110_000 and alpha["overdue"] == 60_000
    assert r.trace.row_table == "invoices"


def test_payable_aging_and_payment_behavior():
    r = aging(invoices_df(), AS_OF, "payable")
    assert r.buckets["31-60"] == 40_000
    pb = payment_behavior(invoices_df())
    assert pb["Beta"]["avg_days_late"] == 15


def test_cost_drivers_vs_previous_period():
    df = make_txn_df([
        (1, "2026-08-05", 20_000, "out", "rent"), (2, "2026-08-06", 10_000, "out", "transport"),
        (3, "2026-09-05", 20_000, "out", "rent"), (4, "2026-09-06", 25_000, "out", "transport"),
        (5, "2026-09-07", 5_000, "out", "marketing")])
    r = top_cost_drivers(df, date(2026, 9, 1), date(2026, 9, 30))
    assert r.total_expense == 50_000
    t = next(d for d in r.drivers if d.category == "transport")
    assert t.share_pct == 50.0 and t.change == 15_000 and t.change_pct == 150.0
    m = next(d for d in r.drivers if d.category == "marketing")
    assert m.previous_amount == 0 and m.change_pct is None


def test_explain_change_names_the_drivers():
    df = make_txn_df([
        (1, "2026-08-10", 300_000, "in", "sales", "Karim Knit"), (2, "2026-08-11", 100_000, "out", "inventory"),
        (3, "2026-09-10", 200_000, "in", "sales", "Karim Knit"), (4, "2026-09-11", 160_000, "out", "inventory")])
    r = explain_change(df, date(2026, 9, 1), date(2026, 9, 30), "September 2026")
    assert r.previous_net == 200_000 and r.current_net == 40_000 and r.net_change == -160_000
    assert r.drivers[0].category == "sales" and r.drivers[0].effect_on_net == -100_000
    assert r.customer_changes[0]["counterparty"] == "Karim Knit" and r.customer_changes[0]["change"] == -100_000
    text = " ".join(r.explanation)
    assert "fell by ৳1,60,000" in text and "slow-moving inventory" in text


def test_seasonality_detects_eid_peak():
    rows, i = [], 0
    for y, m in [(2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5),
                 (2026, 6), (2026, 7), (2026, 8), (2026, 9)]:
        i += 1
        amt = 400_000 if (y, m) == (2026, 3) else 200_000
        rows.append((i, f"{y}-{m:02d}-12", amt, "in", "sales"))
    r = seasonality(make_txn_df(rows), AS_OF)
    assert r.peaks == ["2026-03"]
    peak = next(x for x in r.months if x.month == "2026-03")
    assert any("Eid ul-Fitr" in e for e in peak.events)
    assert any("Eid ul-Fitr" in s for s in r.insights)
    assert r.revenue_cv is not None and r.revenue_cv > 0


def test_business_metrics_for_lending():
    class B:
        established_on = date(2023, 1, 1)
        existing_monthly_debt_service = 0
        collateral_value = 500_000
        has_trade_license = True
        has_tin = True
        has_bank_account = True
        vat_registered = False
        women_led = True
        sector = "accessories"

    df = three_months()
    m = business_metrics(df, invoices_df(), B(), AS_OF)
    # Only Jul-Sep in the 6m window: operating profit 180k / 6 = 30k; repayments 60k / 6 = 10k
    assert m.avg_monthly_operating_cash_flow_6m == 30_000
    assert m.existing_monthly_debt_service == 10_000 and m.existing_dscr == 3.0
    assert m.business_age_months == 45 and m.receivables_overdue == 140_000
