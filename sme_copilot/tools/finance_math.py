"""Pure, deterministic loan and ratio math. No I/O, fully unit-tested.

Conventions: rates are annual percentages (12.5 means 12.5 % p.a.); tenure in months;
amounts in BDT. Results are rounded to 2 dp only at the edges.
"""
from __future__ import annotations

from dataclasses import dataclass


def emi_reducing(principal: float, annual_rate_pct: float, months: int) -> float:
    """Equated monthly instalment on a reducing-balance loan.

    EMI = P * r * (1+r)^n / ((1+r)^n - 1),  r = annual_rate / 12 / 100
    """
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate_pct / 1200.0
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def emi_flat(principal: float, annual_flat_rate_pct: float, months: int) -> float:
    """Flat-rate instalment (common in microfinance): interest charged on the full principal
    for the whole tenure. EMI = (P + P * rate * n/12) / n"""
    if principal <= 0 or months <= 0:
        return 0.0
    interest = principal * annual_flat_rate_pct / 100 * months / 12
    return (principal + interest) / months


def max_principal_for_emi(emi: float, annual_rate_pct: float, months: int) -> float:
    """Inverse of emi_reducing: the largest loan a given monthly payment can service."""
    if emi <= 0 or months <= 0:
        return 0.0
    r = annual_rate_pct / 1200.0
    if r == 0:
        return emi * months
    return emi * (1 - (1 + r) ** -months) / r


def irr_monthly(net_disbursed: float, payment: float, months: int) -> float:
    """Monthly rate r such that the PV of ``months`` payments equals ``net_disbursed``.
    Bisection: robust and dependency-free."""
    if net_disbursed <= 0 or payment <= 0 or months <= 0:
        return 0.0
    if payment * months <= net_disbursed:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        pv = payment * (1 - (1 + mid) ** -months) / mid if mid > 0 else payment * months
        if pv > net_disbursed:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass
class CreditCost:
    principal: float
    months: int
    rate_pct: float
    method: str  # reducing | flat
    emi: float
    total_repayment: float
    total_interest: float
    fees: float
    total_cost_of_credit: float  # interest + fees
    effective_apr_pct: float  # true annual cost incl. fees and flat-rate effect (nominal, x12)

    def as_dict(self) -> dict:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def cost_of_credit(principal: float, annual_rate_pct: float, months: int, *, method: str = "reducing",
                   fee_pct: float = 0.0, fixed_fees: float = 0.0) -> CreditCost:
    """EMI, total repayment and total cost of credit, including upfront fees.

    The effective APR solves for the rate that equates instalments with the cash the borrower
    actually receives (principal minus upfront fees), so flat-rate and fee-heavy loans can be
    compared fairly with reducing-balance loans.
    """
    emi = emi_flat(principal, annual_rate_pct, months) if method == "flat" else \
        emi_reducing(principal, annual_rate_pct, months)
    total = emi * months
    fees = principal * fee_pct / 100 + fixed_fees
    interest = total - principal
    apr = irr_monthly(principal - fees, emi, months) * 12 * 100
    return CreditCost(principal=principal, months=months, rate_pct=annual_rate_pct, method=method, emi=emi,
                      total_repayment=total, total_interest=interest, fees=fees,
                      total_cost_of_credit=interest + fees, effective_apr_pct=apr)


def amortization(principal: float, annual_rate_pct: float, months: int) -> list[dict]:
    """Reducing-balance schedule: month, payment, interest, principal, balance."""
    emi = emi_reducing(principal, annual_rate_pct, months)
    r = annual_rate_pct / 1200.0
    bal = principal
    rows = []
    for m in range(1, months + 1):
        interest = bal * r
        princ = emi - interest
        if m == months:
            princ = bal
        bal = max(0.0, bal - princ)
        rows.append({"month": m, "payment": round(interest + princ, 2), "interest": round(interest, 2),
                     "principal": round(princ, 2), "balance": round(bal, 2)})
    return rows


def dscr(monthly_operating_cash_flow: float, monthly_debt_service: float) -> float | None:
    """Debt service coverage ratio = cash available for debt service / debt service.
    None when there is no debt service (ratio undefined / infinite)."""
    if monthly_debt_service <= 0:
        return None
    return monthly_operating_cash_flow / monthly_debt_service


def runway_months(cash: float, monthly_net_burn: float) -> float | None:
    """Months until cash runs out at the current burn. None if not burning cash."""
    if monthly_net_burn <= 0:
        return None
    return max(0.0, cash) / monthly_net_burn


def coefficient_of_variation(values: list[float]) -> float | None:
    """std / mean (population). Lower = more stable revenue."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    if mean == 0:
        return None
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return var ** 0.5 / mean


def safe_div(a: float, b: float) -> float | None:
    return a / b if b else None
