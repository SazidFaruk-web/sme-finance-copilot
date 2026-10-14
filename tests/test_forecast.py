"""Forecast, what-if, recurring detection, alerts and digest."""
from datetime import date, timedelta

import pandas as pd
import pytest

from sme_copilot.agent.orchestrator import Agent
from sme_copilot.forecasting.alerts import compliance_due_dates, refresh_alerts
from sme_copilot.forecasting.digest import build_digest
from sme_copilot.forecasting.forecast import (
    Flow,
    ForecastInputs,
    build_inputs,
    detect_recurring,
    project,
)
from sme_copilot.forecasting.whatif import Scenario, simulate
from sme_copilot.models import Alert, Obligation
from sme_copilot.tools import repo
from tests.conftest import make_ctx, make_txn_df

AS_OF = date(2026, 10, 14)


def simple_inputs(**kw) -> ForecastInputs:
    base = dict(as_of=AS_OF, horizon=90, start_balance=100_000, base_in_daily=1_000, base_out_variable_daily=400,
                base_out_fixed_daily=100, month_factor={}, scheduled=[], recurring=[], weekly_std=0.0,
                low_threshold=50_000)
    base.update(kw)
    return ForecastInputs(**base)


def test_projection_arithmetic_is_exact():
    inp = simple_inputs(scheduled=[Flow(AS_OF + timedelta(days=10), -30_000, "Rent", "obligation"),
                                   Flow(AS_OF + timedelta(days=20), 50_000, "Collection", "receivable")])
    r = project(inp)
    s30 = r.summaries[0]
    # 30 days * 500 net baseline + 50k - 30k = 35,000 gain
    assert s30.end_balance == pytest.approx(135_000)
    assert s30.total_inflow == pytest.approx(80_000) and s30.total_outflow == pytest.approx(45_000)
    day10 = r.series[9]
    assert day10.balance == pytest.approx(100_000 + 10 * 500 - 30_000) and "Rent" in day10.events[0]
    assert r.summaries[-1].days == 90 and r.first_negative_date is None
    assert r.series[0].low == r.series[0].high  # zero volatility -> zero band


def test_first_negative_and_runway():
    r = project(simple_inputs(start_balance=10_000, base_in_daily=0, base_out_variable_daily=0,
                              base_out_fixed_daily=1_000))
    assert r.first_negative_date == AS_OF + timedelta(days=11)
    assert r.first_below_threshold_date == AS_OF + timedelta(days=1)
    assert r.runway_months == pytest.approx(10_000 / 30_000, abs=0.05)


def test_uncertainty_band_grows_with_sqrt_time():
    r = project(simple_inputs(weekly_std=1_000))
    w1 = r.series[0].high - r.series[0].low
    w4 = r.series[3].high - r.series[3].low
    assert w4 == pytest.approx(2 * w1, rel=1e-3)


def test_detect_recurring_rent_and_salary():
    rows, i = [], 0
    for m in (6, 7, 8, 9):
        i += 1
        rows.append((i, f"2026-{m:02d}-01", 30_000, "out", "rent"))
        i += 1
        rows.append((i, f"2026-{m:02d}-28", 45_000 + (m % 2) * 1000, "out", "salary"))
        i += 1
        rows.append((i, f"2026-{m:02d}-15", 5_000 * m, "out", "transport"))
    rec = {r.category: r for r in detect_recurring(make_txn_df(rows), AS_OF)}
    assert rec["rent"].amount == 30_000 and rec["rent"].day_of_month == 1
    assert rec["salary"].day_of_month == 28
    assert "transport" not in rec


def test_whatif_delay_and_loan():
    inp = simple_inputs(scheduled=[Flow(AS_OF + timedelta(days=5), 200_000, "Collection INV-1", "receivable",
                                        category="Karim Knit"),
                                   Flow(AS_OF + timedelta(days=12), -150_000, "Supplier", "payable")],
                        start_balance=20_000, base_in_daily=0, base_out_variable_daily=0, base_out_fixed_daily=0)
    r = simulate(inp, [Scenario(kind="delay_receivable", customer="biggest", days=20)])
    assert r.scenarios[0].applied and "Karim Knit" in r.scenarios[0].description
    assert r.end_balance_change == 0  # same money, later
    assert r.scenario_min_balance == pytest.approx(20_000 - 150_000)
    assert r.scenario_first_negative_date == AS_OF + timedelta(days=12)
    assert r.baseline_first_negative_date is None
    r2 = simulate(inp, [Scenario(kind="delay_receivable", customer="biggest", days=20),
                        Scenario(kind="loan", amount=500_000, annual_rate_pct=12, months=24, start_in_days=7)])
    assert r2.scenario_first_negative_date is None and r2.loan_emi == pytest.approx(23_536.74, abs=0.01)
    assert any("avoids" in x or "balance would be" in x for x in r2.explanation)


def test_whatif_revenue_and_expense_changes():
    inp = simple_inputs()
    down = simulate(inp, [Scenario(kind="revenue_change", pct=-20)])
    # baseline net/day 500; with -20% sales: 800 - 320 - 100 = 380 -> 120/day less over 90 days
    assert down.end_balance_change == pytest.approx(-120 * 90)
    hire = simulate(inp, [Scenario(kind="expense_change", category="salary", monthly_amount=15_000)])
    assert hire.end_balance_change == pytest.approx(-15_000 * 3)


def test_scenario_validation():
    with pytest.raises(ValueError):
        Scenario(kind="loan")
    with pytest.raises(ValueError):
        Scenario(kind="expense_change", category="rent")


def test_forecast_on_seeded_business_uses_invoices_and_recurring(seeded):
    db, b = seeded["db"], seeded["business"]
    inp = build_inputs(repo.load_transactions(db, b.id), repo.load_invoices(db, b.id), [], b, AS_OF, 90)
    cats = {r.category for r in inp.recurring}
    assert {"rent", "salary"} <= cats
    rec = [f for f in inp.scheduled if f.kind == "receivable"]
    assert {f.category for f in rec} == {"Karim Knit Composite"}
    # INV-201 is overdue -> pulled into the next week; INV-203 due 31 Oct + Karim's usual delay (none on record)
    assert min(f.day for f in rec) == AS_OF + timedelta(days=7)
    res = project(inp)
    assert res.start_balance == pytest.approx(200_000 + 900_000 - 720_000)


def test_explicit_obligation_overrides_detection(seeded):
    db, b = seeded["db"], seeded["business"]
    obl = [Obligation(business_id=b.id, name="Shop rent", category="rent", amount=35_000, day_of_month=5,
                      next_due=date(2026, 11, 5), frequency="monthly")]
    inp = build_inputs(repo.load_transactions(db, b.id), repo.load_invoices(db, b.id), obl, b, AS_OF, 90)
    rents = [f for f in inp.scheduled if f.category == "rent"]
    assert [f.day for f in rents] == [date(2026, 11, 5), date(2026, 12, 5), date(2027, 1, 5)]
    assert all(f.amount == -35_000 for f in rents)


def test_alerts_overdue_and_dedupe(seeded):
    db, b = seeded["db"], seeded["business"]
    first = refresh_alerts(db, b, AS_OF)
    kinds = {a.kind for a in first}
    assert "overdue_invoice" in kinds
    od = next(a for a in first if a.kind == "overdue_invoice")
    assert "Karim" in od.title and od.data["suggested_tool"]["name"] == "create_payment_reminder"
    n = db.query(Alert).count()
    refresh_alerts(db, b, AS_OF)
    assert db.query(Alert).count() == n  # idempotent
    od.status = "dismissed"
    db.flush()
    again = refresh_alerts(db, b, AS_OF)
    assert od.id not in {a.id for a in again}  # dismissed stays dismissed


def test_compliance_reminders_are_marked_verify(seeded):
    b = seeded["business"]
    b.vat_registered = True
    due = compliance_due_dates(b, date(2026, 11, 8))
    ids = {r["id"] for r, _ in due}
    assert "vat_monthly_return" in ids
    assert all(r["verified"] is False for r, _ in due)


def test_digest_has_actions(seeded):
    d = build_digest(seeded["db"], seeded["business"], AS_OF)
    assert d.kpis["cash_balance"] == pytest.approx(380_000)
    assert any(a.tool == "create_payment_reminder" for a in d.actions)


@pytest.mark.parametrize("q,tool", [
    ("Forecast my cash flow for the next 60 days", "forecast_cash_flow"),
    ("আগামী ৩০ দিনে আমার নগদ কেমন থাকবে?", "forecast_cash_flow"),
    ("What if my biggest customer pays 20 days late?", "run_what_if"),
    ("jodi 5 lakh taka loan nei 12% e 24 mash er jonno?", "run_what_if"),
    ("What needs my attention this week?", "get_digest"),
    ("remind me to pay VAT on 15th", "schedule_alert"),
])
def test_agent_routes_forecast_questions(seeded, q, tool):
    r = Agent().run(make_ctx(seeded), q)
    assert r.tool_calls and r.tool_calls[0]["tool"] == tool and r.tool_calls[0]["status"] == "ok", r.tool_calls
    assert r.ungrounded_numbers == [], (r.reply, r.ungrounded_numbers)
    if tool in ("forecast_cash_flow", "run_what_if"):
        assert r.disclaimer


def test_whatif_loan_args_parsed_from_banglish(seeded):
    r = Agent().run(make_ctx(seeded), "jodi 5 lakh taka loan nei 12% e 24 mash er jonno?")
    sc = r.tool_calls[0]["args"]["scenarios"][0]
    assert sc["kind"] == "loan" and sc["amount"] == 500_000 and sc["annual_rate_pct"] == 12 and sc["months"] == 24
    assert r.language == "banglish"
