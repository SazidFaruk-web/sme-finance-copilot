import pytest

from sme_copilot.tools.finance_math import (
    amortization,
    coefficient_of_variation,
    cost_of_credit,
    dscr,
    emi_flat,
    emi_reducing,
    irr_monthly,
    max_principal_for_emi,
    runway_months,
)
from sme_copilot.tools.money import format_bdt, group_lakh, parse_amount, words_lakh


def test_emi_reducing_known_value():
    # 1 lakh at 12% p.a. for 12 months: the standard textbook answer is 8,884.88
    assert emi_reducing(100_000, 12, 12) == pytest.approx(8884.88, abs=0.01)


def test_emi_zero_rate_and_bad_inputs():
    assert emi_reducing(120_000, 0, 12) == 10_000
    assert emi_reducing(0, 10, 12) == 0 and emi_reducing(1000, 10, 0) == 0


def test_emi_flat():
    assert emi_flat(100_000, 10, 12) == pytest.approx(9166.67, abs=0.01)


def test_max_principal_inverts_emi():
    emi = emi_reducing(500_000, 13.5, 36)
    assert max_principal_for_emi(emi, 13.5, 36) == pytest.approx(500_000, rel=1e-9)


def test_flat_rate_effective_apr_is_much_higher():
    c = cost_of_credit(100_000, 10, 12, method="flat")
    assert c.total_interest == pytest.approx(10_000, abs=0.01)
    assert 17.5 < c.effective_apr_pct < 18.5  # well-known ~18% APR for a 10% flat 1-year loan


def test_fees_raise_effective_apr_and_total_cost():
    no_fee = cost_of_credit(500_000, 12, 24)
    fee = cost_of_credit(500_000, 12, 24, fee_pct=1.0, fixed_fees=2_000)
    assert no_fee.effective_apr_pct == pytest.approx(12, abs=0.01)
    assert fee.fees == pytest.approx(7_000)
    assert fee.total_cost_of_credit == pytest.approx(no_fee.total_interest + 7_000, abs=0.01)
    assert fee.effective_apr_pct > 12.5


def test_amortization_schedule_closes_to_zero():
    rows = amortization(300_000, 11, 24)
    assert rows[-1]["balance"] == 0
    assert sum(r["principal"] for r in rows) == pytest.approx(300_000, abs=0.05)
    assert rows[0]["interest"] == pytest.approx(300_000 * 0.11 / 12, abs=0.01)


def test_irr_edge_cases():
    assert irr_monthly(0, 100, 12) == 0
    assert irr_monthly(1200, 100, 12) == 0  # no interest


def test_dscr_runway_cv():
    assert dscr(150_000, 100_000) == 1.5
    assert dscr(150_000, 0) is None
    assert runway_months(300_000, 100_000) == 3
    assert runway_months(300_000, -5) is None
    assert coefficient_of_variation([100, 100, 100]) == 0
    assert coefficient_of_variation([50, 150]) == pytest.approx(0.5)
    assert coefficient_of_variation([1]) is None


@pytest.mark.parametrize("raw,expected", [
    ("৳1,20,000.50", 120000.5), ("Tk 500", 500), ("(2,000)", -2000), ("১৫০০", 1500), ("1500 Dr", 1500),
    (1500, 1500.0), ("", None), ("abc", None), (float("nan"), None), ("-300", -300),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_format_bdt_lakh_and_international():
    assert group_lakh("12345678") == "1,23,45,678"
    assert format_bdt(1234567) == "৳12,34,567"
    assert format_bdt(1234567, style="intl") == "৳1,234,567"
    assert format_bdt(-1500.5, decimals=2) == "-৳1,500.50"
    assert format_bdt(25000, bangla_digits=True) == "৳২৫,০০০"
    assert words_lakh(2_500_000) == "25 lakh" and words_lakh(25_000_000) == "2.5 crore"
