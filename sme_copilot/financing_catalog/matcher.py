"""Financing-option matching using the business's real analysed numbers.

For each catalog product:
  1. Eligibility checks (hard = disqualifying, soft = adjust the offer), each explained.
  2. Affordability: the largest loan whose EMI keeps
         DSCR = monthly operating cash flow / (existing debt service + new EMI) >= product minimum.
  3. Offer = min(requested, product max, affordable[, advance-rate x open receivables]).
  4. Cost at the product's min / mid / max rate: EMI, total repayment, total cost of credit, APR.
  5. Fit score (0-100) for ranking: cost 40, DSCR headroom 20, amount fit 20, speed 10, no-collateral 10.

Every product appears either in ``recommendations`` (with reasons and cautions) or in
``rejected`` (with the specific failed rules). Catalog figures are illustrative until verified.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from sme_copilot.tools.analysis import BusinessMetrics
from sme_copilot.tools.finance_math import cost_of_credit, emi_reducing, emi_flat, max_principal_for_emi
from sme_copilot.tools.money import format_bdt
from sme_copilot.tools.trace import Trace, fmt

from .loader import Catalog, Product, load_catalog

DISCLAIMER = ("Decision support only, not licensed financial advice. All financing figures are illustrative "
              "placeholders until verified with the lender; approval is never guaranteed and depends on the "
              "lender's own assessment.")


class Check(BaseModel):
    rule: str
    passed: bool
    hard: bool
    detail: str


class CostBand(BaseModel):
    rate_pct: float
    emi: float
    total_repayment: float
    total_cost_of_credit: float
    effective_apr_pct: float


class Match(BaseModel):
    product_id: str
    name: str
    lender_type: str
    eligible: bool
    score: float
    requested_amount: float
    offered_amount: float
    tenure_months: int
    rate_method: str
    cost_low: CostBand | None
    cost_mid: CostBand | None
    cost_high: CostBand | None
    dscr_after: float | None
    min_dscr: float
    collateral: str
    speed_days: int
    documents: list[dict[str, Any]]
    checks: list[Check]
    reasons: list[str]
    cautions: list[str]
    verify_label: str
    source_url: str | None
    last_verified_date: str | None


class MatchResult(BaseModel):
    requested_amount: float
    amount_basis: str
    purpose: str
    tenure_months: int
    metrics: dict[str, Any]
    recommendations: list[Match]
    rejected: list[Match]
    disclaimer: str
    trace: Trace


def _cost(p: Product, amount: float, months: int, rate: float) -> CostBand:
    c = cost_of_credit(amount, rate, months, method=p.rate_method, fee_pct=p.fees_pct)
    return CostBand(rate_pct=rate, emi=round(c.emi, 2), total_repayment=round(c.total_repayment, 2),
                    total_cost_of_credit=round(c.total_cost_of_credit, 2), effective_apr_pct=round(c.effective_apr_pct, 2))


def _emi(p: Product, amount: float, months: int, rate: float) -> float:
    return emi_flat(amount, rate, months) if p.rate_method == "flat" else emi_reducing(amount, rate, months)


def _affordable(p: Product, m: BusinessMetrics, months: int) -> float:
    """Largest principal keeping DSCR >= product minimum at the product's mid rate."""
    max_emi = m.avg_monthly_operating_cash_flow_6m / p.eligibility.min_dscr - m.existing_monthly_debt_service
    if max_emi <= 0:
        return 0.0
    if p.rate_method == "flat":
        # flat EMI = P(1 + r*n/12)/n  ->  P = EMI*n / (1 + r*n/12)
        return max_emi * months / (1 + p.mid_rate / 100 * months / 12)
    return max_principal_for_emi(max_emi, p.mid_rate, months)


def _docs(p: Product, business: Any, catalog: Catalog) -> list[dict[str, Any]]:
    out = []
    for d in p.documents_required:
        spec = catalog.documents.get(d, {"label": d})
        flag = spec.get("business_flag")
        if spec.get("generated"):
            status = "can_generate"
        elif flag:
            status = "have" if bool(getattr(business, flag, False)) else "missing"
        else:
            status = "to_prepare"
        out.append({"id": d, "label": spec.get("label", d), "status": status})
    return out


def evaluate(p: Product, m: BusinessMetrics, business: Any, amount: float, purpose: str, tenure: int | None,
             open_receivables: float, monthly_purchases: float, catalog: Catalog, style: str = "lakh") -> Match:
    e = p.eligibility
    M = lambda v: format_bdt(v, style=style)  # noqa: E731
    months = max(p.tenure_months_min, min(p.tenure_months_max, tenure or min(24, p.tenure_months_max)))
    checks: list[Check] = []

    def add(rule: str, passed: bool, hard: bool, ok_text: str, fail_text: str) -> None:
        checks.append(Check(rule=rule, passed=passed, hard=hard, detail=ok_text if passed else fail_text))

    age = m.business_age_months
    if age is not None:
        add("business_age", age >= e.min_business_age_months, True,
            f"{age} months in business (minimum {e.min_business_age_months})",
            f"needs {e.min_business_age_months} months in business; you have {age}")
        if e.max_business_age_months is not None:
            add("business_age_max", age <= e.max_business_age_months, True,
                f"business is young enough for this scheme ({age} months)",
                f"meant for businesses under {e.max_business_age_months} months old; you have {age}")
    add("revenue", m.avg_monthly_revenue_6m >= e.min_avg_monthly_revenue, True,
        f"6-month average revenue {M(m.avg_monthly_revenue_6m)} meets the {M(e.min_avg_monthly_revenue)} minimum",
        f"needs average monthly revenue of {M(e.min_avg_monthly_revenue)}; yours is {M(m.avg_monthly_revenue_6m)}")
    if m.revenue_cv_12m is not None:
        add("revenue_stability", m.revenue_cv_12m <= e.max_revenue_cv, False,
            f"revenue stability OK (variation {m.revenue_cv_12m:.2f} <= {e.max_revenue_cv})",
            f"revenue is uneven (variation {m.revenue_cv_12m:.2f} > {e.max_revenue_cv}); lender may ask for more evidence")
    add("records", m.months_of_data >= e.min_months_of_records, True,
        f"{m.months_of_data} months of records (minimum {e.min_months_of_records})",
        f"needs {e.min_months_of_records} months of records; you have {m.months_of_data}")
    if e.requires_trade_license:
        add("trade_license", m.has_trade_license, True, "trade licence on file", "requires a valid trade licence")
    if e.requires_tin:
        add("tin", m.has_tin, True, "e-TIN on file", "requires an e-TIN")
    if e.requires_bank_account:
        add("bank_account", m.has_bank_account, True, "business bank account on file", "requires a bank account")
    if e.women_led_only:
        add("women_led", m.women_led, True, "women-led business", "only for women-led businesses")
    if amount < p.min_amount:
        add("min_amount", False, True, "", f"minimum loan is {M(p.min_amount)}; you asked for {M(amount)}")
    if p.collateral_required:
        need = p.collateral_coverage_min * min(amount, p.max_amount)
        add("collateral", m.collateral_value >= need, True,
            f"collateral {M(m.collateral_value)} covers the {int(p.collateral_coverage_min * 100)}% requirement",
            f"needs collateral of about {M(need)}; recorded collateral is {M(m.collateral_value)}")
    if e.requires_open_receivables:
        add("open_receivables", open_receivables > 0, True,
            f"open invoices of {M(open_receivables)} can be financed", "needs unpaid invoices from buyers")

    affordable = _affordable(p, m, months)
    caps = {"requested": amount, "product max": p.max_amount, "debt capacity (DSCR)": affordable}
    if e.requires_open_receivables:
        caps["advance on open invoices"] = open_receivables * e.advance_rate
    if e.max_amount_vs_monthly_purchases is not None and monthly_purchases > 0:
        caps["typical supplier limit"] = monthly_purchases * e.max_amount_vs_monthly_purchases
    binding = min(caps, key=caps.get)
    offered = max(0.0, round(min(caps.values()), -3))
    if offered < p.min_amount:
        add("affordability", False, True, "",
            f"your cash flow supports only about {M(max(affordable, 0))} at a {e.min_dscr} DSCR, below the "
            f"{M(p.min_amount)} minimum")
    elif offered < amount:
        add("affordability", True, False, f"offer limited to {M(offered)} by {binding}", "")

    hard_fail = [c for c in checks if c.hard and not c.passed]
    eligible = not hard_fail and offered > 0
    lo = mid = hi = None
    dscr_after = None
    if offered > 0:
        lo = _cost(p, offered, months, p.interest_rate_min_pct)
        mid = _cost(p, offered, months, p.mid_rate)
        hi = _cost(p, offered, months, p.interest_rate_max_pct)
        ds = m.existing_monthly_debt_service + mid.emi
        dscr_after = round(m.avg_monthly_operating_cash_flow_6m / ds, 2) if ds > 0 else None

    reasons, cautions = [], []
    if eligible:
        reasons = [c.detail for c in checks if c.passed][:5]
        if dscr_after is not None:
            reasons.append(f"after this loan your DSCR would be about {dscr_after} (minimum {e.min_dscr})")
        if purpose not in p.purposes:
            cautions.append(f"usually used for {', '.join(p.purposes)}, not '{purpose}'")
        cautions += [c.detail for c in checks if not c.passed and not c.hard]
        if p.rate_method == "flat":
            cautions.append("flat-rate pricing: the true annual cost (APR) is higher than the headline rate")
        if not p.collateral_required and "guarantee" in p.collateral.lower():
            cautions.append("needs a personal guarantee or guarantor")
        missing_docs = [d["label"] for d in _docs(p, business, catalog) if d["status"] == "missing"]
        if missing_docs:
            cautions.append("missing documents: " + ", ".join(missing_docs))
    else:
        reasons = [c.detail for c in hard_fail] or ["not affordable with current cash flow"]

    score = 0.0
    if eligible and mid:
        cost_score = max(0.0, 1 - mid.effective_apr_pct / 30) * 40
        headroom = ((dscr_after or e.min_dscr) - e.min_dscr) / e.min_dscr if dscr_after else 1
        score = cost_score + min(1.0, max(0.0, headroom)) * 20 + min(1.0, offered / amount) * 20 + \
            max(0.0, 1 - p.speed_days / 60) * 10 + (10 if not p.collateral_required else 0)
        if purpose not in p.purposes:
            score *= 0.8
    return Match(product_id=p.id, name=p.name, lender_type=p.lender_type, eligible=eligible, score=round(score, 1),
                 requested_amount=amount, offered_amount=offered if eligible else 0, tenure_months=months,
                 rate_method=p.rate_method, cost_low=lo, cost_mid=mid, cost_high=hi, dscr_after=dscr_after,
                 min_dscr=e.min_dscr, collateral=p.collateral, speed_days=p.speed_days,
                 documents=_docs(p, business, catalog), checks=checks, reasons=reasons, cautions=cautions,
                 verify_label=p.verify_label, source_url=p.source_url,
                 last_verified_date=p.last_verified_date.isoformat() if p.last_verified_date else None)


def match(metrics: BusinessMetrics, business: Any, *, amount: float | None, purpose: str = "working_capital",
          tenure_months: int | None = None, open_receivables: float = 0.0, monthly_purchases: float = 0.0,
          suggested_amount: float | None = None, suggested_basis: str = "", catalog: Catalog | None = None,
          style: str = "lakh", top_n: int | None = None) -> MatchResult:
    cat = catalog or load_catalog()
    if amount is None:
        amount = suggested_amount or max(50_000.0, round(metrics.avg_monthly_revenue_6m * 0.5, -4))
        basis = suggested_basis or "no amount given: suggested ~half a month of revenue as working capital"
    else:
        basis = "amount requested by user"
    results = [evaluate(p, metrics, business, amount, purpose, tenure_months, open_receivables, monthly_purchases,
                        cat, style) for p in cat.products]
    elig = sorted([r for r in results if r.eligible], key=lambda r: -r.score)
    rej = [r for r in results if not r.eligible]
    t = Trace(formula="eligible if all hard rules pass; offer = min(request, product max, DSCR capacity); "
                      "EMI = P*r*(1+r)^n/((1+r)^n-1); score = cost 40 + DSCR headroom 20 + amount fit 20 + speed 10 "
                      "+ no collateral 10", period=f"metrics as of {metrics.as_of}")
    t.step("Requested amount", amount, basis)
    t.step("Average monthly operating cash flow (6m)", metrics.avg_monthly_operating_cash_flow_6m)
    t.step("Existing monthly debt service", metrics.existing_monthly_debt_service)
    t.step("Average monthly revenue (6m)", metrics.avg_monthly_revenue_6m)
    t.step("Revenue variation (CV, 12m)", metrics.revenue_cv_12m)
    t.step("Business age (months)", metrics.business_age_months)
    for r in elig[:3]:
        t.step(f"{r.name}: offer / EMI (mid rate)", r.offered_amount,
               f"EMI {fmt(r.cost_mid.emi) if r.cost_mid else '-'} over {r.tenure_months} months, score {r.score}")
    t.row_ids, t.row_count, t.sources = metrics.trace.row_ids, metrics.trace.row_count, metrics.trace.sources
    t.assumptions += ["All catalog terms are illustrative until verified with the lender.",
                      "Affordability uses the product's mid-point rate."]
    return MatchResult(requested_amount=amount, amount_basis=basis, purpose=purpose,
                       tenure_months=tenure_months or 24,
                       metrics={k: v for k, v in metrics.model_dump(mode="json").items() if k != "trace"},
                       recommendations=elig[:top_n] if top_n else elig, rejected=rej, disclaimer=DISCLAIMER, trace=t)
