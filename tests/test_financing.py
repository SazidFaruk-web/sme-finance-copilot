"""Financing catalog validation, matcher eligibility/affordability/cost, readiness score."""
from datetime import date

import pytest
import yaml
from pydantic import ValidationError

from sme_copilot.agent.orchestrator import Agent
from sme_copilot.financing_catalog.loader import Catalog, Product, load_catalog
from sme_copilot.financing_catalog.matcher import evaluate, match
from sme_copilot.financing_catalog.readiness import readiness
from sme_copilot.tools.analysis import BusinessMetrics
from sme_copilot.tools.finance_math import emi_reducing, max_principal_for_emi
from sme_copilot.tools.trace import Trace
from tests.conftest import make_ctx


def metrics(**kw) -> BusinessMetrics:
    base = dict(as_of=date(2026, 10, 14), months_of_data=18, business_age_months=40, avg_monthly_revenue_6m=400_000,
                avg_monthly_revenue_12m=380_000, revenue_cv_12m=0.3, avg_monthly_operating_cash_flow_6m=60_000,
                existing_monthly_debt_service=0, existing_dscr=None, gross_margin_pct_6m=30.0, net_margin_pct_6m=15.0,
                receivables_overdue=50_000, collateral_value=1_000_000, has_trade_license=True, has_tin=True,
                has_bank_account=True, vat_registered=False, women_led=False, sector="accessories", trace=Trace())
    base.update(kw)
    return BusinessMetrics(**base)


class Biz:
    has_trade_license = True
    has_tin = True
    has_bank_account = True
    women_led = False


def prod(**kw) -> Product:
    base = dict(id="p", name="Test loan", lender_type="commercial_bank", product_type="term_loan",
                purposes=["working_capital"], min_amount=100_000, max_amount=2_000_000, interest_rate_min_pct=10,
                interest_rate_max_pct=14, tenure_months_min=12, tenure_months_max=36,
                eligibility={"min_business_age_months": 24, "min_avg_monthly_revenue": 200_000, "min_dscr": 1.25,
                             "min_months_of_records": 12, "requires_trade_license": True})
    base.update(kw)
    return Product(**base)


def test_shipped_catalog_is_valid_and_all_illustrative():
    cat = load_catalog()
    assert len(cat.products) >= 10
    types = {p.lender_type for p in cat.products}
    assert {"commercial_bank", "mfi", "refinance_scheme", "mfs_partner", "supplier", "nbfi", "bank_or_fintech"} <= types
    for p in cat.products:
        assert p.illustrative and not p.verified and p.verify_label.startswith("Illustrative")
        assert p.last_verified_date is None
        for d in p.documents_required:
            assert d in cat.documents, f"{p.id}: undefined document {d}"


def test_catalog_rejects_bad_ranges():
    with pytest.raises(ValidationError):
        prod(min_amount=500_000, max_amount=100_000)
    with pytest.raises(ValidationError):
        prod(interest_rate_min_pct=15, interest_rate_max_pct=10)


def test_affordability_caps_offer_by_dscr():
    m = metrics(avg_monthly_operating_cash_flow_6m=60_000)
    p = prod()
    r = evaluate(p, m, Biz(), 2_000_000, "working_capital", 24, 0, 0, Catalog(products=[p]))
    max_emi = 60_000 / 1.25
    expected = round(max_principal_for_emi(max_emi, 12, 24), -3)
    assert r.eligible and r.offered_amount == expected
    assert r.cost_mid.emi == pytest.approx(emi_reducing(expected, 12, 24), abs=0.01)
    assert r.dscr_after == pytest.approx(60_000 / r.cost_mid.emi, abs=0.01) and r.dscr_after >= 1.25
    assert any("DSCR" in c.detail or "debt capacity" in c.detail for c in r.checks)


def test_hard_rule_rejections_are_explained():
    p = prod()
    young = evaluate(p, metrics(business_age_months=10), Biz(), 300_000, "working_capital", 24, 0, 0, Catalog(products=[p]))
    assert not young.eligible and "24 months" in young.reasons[0]

    class NoLicence(Biz):
        has_trade_license = False

    nolic = evaluate(p, metrics(has_trade_license=False), NoLicence(), 300_000, "working_capital", 24, 0, 0,
                     Catalog(products=[p]))
    assert not nolic.eligible and any("trade licence" in r for r in nolic.reasons)
    broke = evaluate(p, metrics(avg_monthly_operating_cash_flow_6m=1_000), Biz(), 300_000, "working_capital", 24, 0, 0,
                     Catalog(products=[p]))
    assert not broke.eligible and any("cash flow supports only" in r for r in broke.reasons)


def test_collateral_and_women_led_rules():
    p = prod(collateral_required=True, collateral_coverage_min=0.5)
    r = evaluate(p, metrics(collateral_value=100_000), Biz(), 1_000_000, "working_capital", 24, 0, 0,
                 Catalog(products=[p]))
    assert not r.eligible and any("collateral" in x for x in r.reasons)
    w = prod(eligibility={"women_led_only": True})
    assert not evaluate(w, metrics(women_led=False), Biz(), 300_000, "working_capital", 24, 0, 0,
                        Catalog(products=[w])).eligible
    assert evaluate(w, metrics(women_led=True), Biz(), 300_000, "working_capital", 24, 0, 0,
                    Catalog(products=[w])).eligible


def test_invoice_financing_limited_by_open_receivables():
    p = prod(eligibility={"requires_open_receivables": True, "advance_rate": 0.8})
    r = evaluate(p, metrics(), Biz(), 1_000_000, "receivables_gap", 3, 200_000, 0, Catalog(products=[p]))
    assert r.offered_amount == 160_000
    none = evaluate(p, metrics(), Biz(), 1_000_000, "receivables_gap", 3, 0, 0, Catalog(products=[p]))
    assert not none.eligible


def test_flat_rate_products_flagged():
    p = prod(rate_method="flat", min_amount=1_000)
    r = evaluate(p, metrics(), Biz(), 50_000, "working_capital", 12, 0, 0, Catalog(products=[p]))
    assert any("flat-rate" in c for c in r.cautions)
    assert r.cost_mid.effective_apr_pct > r.cost_mid.rate_pct


def test_ranking_prefers_cheaper_and_every_product_is_classified():
    res = match(metrics(), Biz(), amount=500_000)
    cat = load_catalog()
    assert len(res.recommendations) + len(res.rejected) == len(cat.products)
    scores = [r.score for r in res.recommendations]
    assert scores == sorted(scores, reverse=True)
    for r in res.recommendations:
        assert r.reasons and r.verify_label.startswith("Illustrative")
    for r in res.rejected:
        assert r.reasons
    assert "not licensed financial advice" in res.disclaimer


def test_readiness_score_components_and_tips():
    strong = readiness(metrics(), receivables_outstanding=500_000)
    assert strong.score >= 80 and strong.band == "strong"
    weak = readiness(metrics(months_of_data=2, business_age_months=8, revenue_cv_12m=0.9, net_margin_pct_6m=-5,
                             has_tin=False, has_trade_license=False, collateral_value=0, receivables_overdue=400_000),
                     receivables_outstanding=500_000)
    assert weak.score < 40 and weak.band == "needs_work"
    assert sum(c.max_points for c in weak.components) == 100
    assert any("e-TIN" in t for t in weak.top_tips)
    assert weak.top_tips[0].endswith("points)")


@pytest.mark.parametrize("q,tool", [
    ("Which loans fit my business for 5 lakh?", "match_financing"),
    ("amar jonno kon loan bhalo?", "match_financing"),
    ("আমি কি ঋণ পাওয়ার যোগ্য? আমার স্কোর কত?", "loan_readiness_score"),
    ("What's my loan readiness score?", "loan_readiness_score"),
    ("EMI for 3 lakh at 12% for 24 months", "calculate_loan"),
])
def test_agent_financing_questions(seeded, q, tool):
    r = Agent().run(make_ctx(seeded), q)
    assert r.tool_calls and r.tool_calls[0]["tool"] == tool and r.tool_calls[0]["status"] == "ok", r.tool_calls
    assert r.disclaimer
    assert r.ungrounded_numbers == [], (r.reply, r.ungrounded_numbers)


def test_match_on_seeded_business_uses_real_numbers(seeded):
    from sme_copilot.agent.executor import execute
    out = execute(make_ctx(seeded), "match_financing", {"amount": 500_000})
    d = out.data
    assert d["metrics"]["avg_monthly_operating_cash_flow_6m"] == pytest.approx(180_000 / (106 / 30), abs=0.01)
    # 180k over the 106 days the records cover (1 Jul - 14 Oct), not over 6 months
    assert any(x["product_id"] == "mfi_microenterprise_loan" for x in d["recommendations"] + d["rejected"])
    assert all(x["offered_amount"] <= 500_000 for x in d["recommendations"])
