"""Financing matching, loan-readiness and catalog tools (Tier 0, advisory)."""
from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from sme_copilot.financing_catalog.loader import load_catalog
from sme_copilot.financing_catalog.matcher import MatchResult, match
from sme_copilot.financing_catalog.readiness import ReadinessResult, readiness, readiness_inputs
from sme_copilot.forecasting.forecast import build_inputs, project
from sme_copilot.tools import repo
from sme_copilot.tools.analysis import business_metrics, resolve_period

from .toolkit import ToolContext, tool


def metrics(ctx: ToolContext):
    return business_metrics(ctx.txns(), ctx.invoices(), ctx.business, ctx.as_of)


class MatchArgs(BaseModel):
    amount: float | None = Field(None, gt=0, le=1e9, description="Loan amount in BDT; omit to get a suggestion "
                                                                  "based on the cash-flow forecast")
    purpose: Literal["working_capital", "inventory", "equipment", "expansion", "seasonal", "receivables_gap"] = \
        "working_capital"
    tenure_months: int | None = Field(None, ge=1, le=120)


@tool("match_financing", "Match Bangladesh SME financing options (bank, refinance schemes, MFI, MFS nano loans, "
      "supplier credit, invoice financing, leasing) to this business using its real numbers: eligibility, offer "
      "amount, EMI, total cost of credit, and a plain-language reason for every recommendation and rejection. "
      "Terms are illustrative until verified.", MatchArgs, 0, category="financing", result_model=MatchResult,
      advisory=True)
def match_financing(ctx: ToolContext, a: MatchArgs):
    m = metrics(ctx)
    inv = ctx.invoices()
    open_ar = 0.0
    if not inv.empty:
        o = inv[(inv["kind"] == "receivable") & inv["status"].isin(["open", "partial"])]
        open_ar = float((o["amount"] - o["amount_paid"]).sum())
    df = ctx.txns()
    s, e, _ = resolve_period("last_3_months", ctx.as_of)
    purchases = 0.0
    if not df.empty:
        p = df[(df["date"] >= pd.Timestamp(s)) & (df["date"] <= pd.Timestamp(e)) & (df["category"] == "inventory")]
        purchases = float(p["amount"].sum()) / 3
    suggested, basis = None, ""
    if a.amount is None:
        fc = project(build_inputs(df, inv, repo.load_obligations(ctx.session, ctx.business.id), ctx.business,
                                  ctx.as_of, 90))
        lowest = min(fc.series, key=lambda x: x.balance)
        gap = fc.low_balance_threshold - lowest.balance
        if gap > 0:
            suggested = max(50_000.0, round(gap * 1.2, -4))
            basis = (f"forecast lowest balance {lowest.balance:,.0f} on {lowest.date} is {gap:,.0f} below your safety "
                     f"level; suggested amount covers that gap +20%")
    return match(m, ctx.business, amount=a.amount, purpose=a.purpose, tenure_months=a.tenure_months,
                 open_receivables=open_ar, monthly_purchases=purchases, suggested_amount=suggested,
                 suggested_basis=basis, style=ctx.style)


class NoArgs(BaseModel):
    pass


@tool("loan_readiness_score", "Loan-readiness score 0-100 with component breakdown (age, records, stability, "
      "profitability, DSCR, documents, receivables, collateral) and point-valued improvement tips.", NoArgs, 0,
      category="financing", result_model=ReadinessResult, advisory=True)
def loan_readiness_score(ctx: ToolContext, a: NoArgs):
    return readiness(metrics(ctx), **readiness_inputs(ctx), style=ctx.style)


class CatalogArgs(BaseModel):
    lender_type: str = Field("", description="optional filter: commercial_bank, refinance_scheme, mfi, mfs_partner, "
                                             "nbfi, supplier, bank_or_fintech")


class CatalogResult(BaseModel):
    count: int
    products: list[dict]
    note: str


@tool("get_financing_catalog", "List financing product types in the catalog with illustrative terms and "
      "verification status.", CatalogArgs, 0, category="financing", result_model=CatalogResult)
def get_financing_catalog(ctx: ToolContext, a: CatalogArgs):
    cat = load_catalog()
    prods = [p for p in cat.products if not a.lender_type or p.lender_type == a.lender_type]
    return CatalogResult(count=len(prods), products=[
        {"id": p.id, "name": p.name, "lender_type": p.lender_type, "amount_range": [p.min_amount, p.max_amount],
         "rate_range_pct": [p.interest_rate_min_pct, p.interest_rate_max_pct], "rate_method": p.rate_method,
         "tenure_months": [p.tenure_months_min, p.tenure_months_max], "collateral": p.collateral,
         "verify_label": p.verify_label, "source_url": p.source_url,
         "last_verified_date": p.last_verified_date.isoformat() if p.last_verified_date else None}
        for p in prods], note="Illustrative catalog: verify every figure with the lender before relying on it.")
