"""Loan-readiness score (0-100) with concrete, point-valued improvement tips.

Not a credit score and not a lender's decision: a transparent checklist of what lenders in
Bangladesh typically look at, computed from the business's own records.

Component (max points):
  business age 10 | record keeping 15 | revenue stability 15 | profitability 15
  debt capacity (DSCR) 15 | documentation 15 | receivables health 10 | collateral 5
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from sme_copilot.tools.analysis import BusinessMetrics
from sme_copilot.tools.money import format_bdt
from sme_copilot.tools.trace import Trace


class Component(BaseModel):
    name: str
    points: float
    max_points: float
    value: str
    tip: str = ""
    potential_gain: float = 0


class ReadinessResult(BaseModel):
    score: float
    band: str
    components: list[Component]
    top_tips: list[str]
    disclaimer: str
    trace: Trace


def _band(score: float) -> str:
    return "strong" if score >= 80 else "good" if score >= 60 else "fair" if score >= 40 else "needs_work"


def readiness(m: BusinessMetrics, *, uncategorized_share: float = 0.0, receivables_outstanding: float = 0.0,
              style: str = "lakh") -> ReadinessResult:
    M = lambda v: format_bdt(v, style=style)  # noqa: E731
    comps: list[Component] = []

    age = m.business_age_months
    pts = 0 if age is None else 10 if age >= 36 else 8 if age >= 24 else 5 if age >= 12 else 2 if age >= 6 else 0
    comps.append(Component(name="Business age", points=pts, max_points=10, value=f"{age} months" if age is not None else "unknown",
                           tip="" if pts == 10 else "Lenders favour businesses with 2-3+ years of history; keep your "
                           "trade licence renewals as proof of age.", potential_gain=10 - pts))

    md = m.months_of_data
    pts = 15 if md >= 12 else 9 if md >= 6 else 5 if md >= 3 else 1
    pts = max(0.0, pts - round(15 * min(uncategorized_share, 0.5), 1))
    comps.append(Component(name="Record keeping", points=pts, max_points=15,
                           value=f"{md} months of records, {round(uncategorized_share * 100)}% uncategorised",
                           tip="" if pts >= 15 else f"Keep recording every sale and expense ({max(0, 12 - md)} more "
                           "months gets full marks) and categorise unclear rows.", potential_gain=15 - pts))

    cv = m.revenue_cv_12m
    pts = 0 if cv is None else 15 if cv <= 0.25 else 11 if cv <= 0.4 else 6 if cv <= 0.6 else 2
    comps.append(Component(name="Revenue stability", points=pts, max_points=15,
                           value=f"variation {cv:.2f}" if cv is not None else "not enough history",
                           tip="" if pts >= 15 else "Smooth revenue by adding off-season products or regular "
                           "customers on monthly orders; deposit sales into the bank account so they are visible.",
                           potential_gain=15 - pts))

    nm = m.net_margin_pct_6m
    pts = 0 if nm is None else 15 if nm >= 15 else 10 if nm >= 8 else 5 if nm >= 0 else 0
    comps.append(Component(name="Profitability", points=pts, max_points=15,
                           value=f"net operating margin {nm}%" if nm is not None else "no revenue",
                           tip="" if pts >= 15 else "Review your top cost drivers and pricing; even 3-5% better "
                           "margin improves repayment capacity.", potential_gain=15 - pts))

    d = m.existing_dscr
    pts = 15 if d is None and m.avg_monthly_operating_cash_flow_6m > 0 else 0 if d is None else \
        15 if d >= 2 else 11 if d >= 1.5 else 7 if d >= 1.25 else 2
    comps.append(Component(name="Debt capacity (DSCR)", points=pts, max_points=15,
                           value=("no existing debt" if d is None else f"DSCR {d}") +
                           f", operating cash flow {M(m.avg_monthly_operating_cash_flow_6m)}/month",
                           tip="" if pts >= 15 else "Pay down expensive existing loans or increase operating "
                           "cash flow before borrowing more.", potential_gain=15 - pts))

    doc_pts = (5 if m.has_trade_license else 0) + (5 if m.has_tin else 0) + (3 if m.has_bank_account else 0) + \
        (2 if m.vat_registered else 0)
    missing = [n for n, ok in (("trade licence", m.has_trade_license), ("e-TIN", m.has_tin),
                               ("business bank account", m.has_bank_account), ("VAT registration (if applicable)",
                                                                               m.vat_registered)) if not ok]
    comps.append(Component(name="Documentation", points=doc_pts, max_points=15,
                           value="missing: " + ", ".join(missing) if missing else "all key documents on file",
                           tip="" if not missing else "Get " + ", ".join(missing) + " - most formal lenders require them.",
                           potential_gain=15 - doc_pts))

    out = receivables_outstanding
    share = (m.receivables_overdue / out) if out > 0 else 0.0
    pts = 10 if share <= 0.1 else 6 if share <= 0.3 else 3 if share <= 0.5 else 0
    comps.append(Component(name="Receivables health", points=pts, max_points=10,
                           value=f"{round(share * 100)}% of receivables overdue ({M(m.receivables_overdue)})",
                           tip="" if pts >= 10 else f"Collect overdue invoices ({M(m.receivables_overdue)}) - send "
                           "reminders; lenders read overdue receivables as cash-flow risk.", potential_gain=10 - pts))

    typical_loan = max(100_000.0, m.avg_monthly_revenue_6m * 3)
    pts = 5 if m.collateral_value >= 0.5 * typical_loan else 2 if m.collateral_value > 0 else 0
    comps.append(Component(name="Collateral", points=pts, max_points=5, value=f"{M(m.collateral_value)} recorded",
                           tip="" if pts >= 5 else "Collateral-free scheme loans exist; otherwise an FDR or "
                           "property helps for larger bank loans.", potential_gain=5 - pts))

    score = round(sum(c.points for c in comps), 1)
    tips = [f"{c.tip} (+up to {c.potential_gain:g} points)" for c in sorted(comps, key=lambda c: -c.potential_gain)
            if c.tip and c.potential_gain > 0][:4]
    t = Trace(formula="score = sum of component points (age 10, records 15, stability 15, profit 15, DSCR 15, "
                      "documents 15, receivables 10, collateral 5)", period=f"as of {m.as_of}")
    for c in comps:
        t.step(c.name, c.points, f"{c.value} -> {c.points:g}/{c.max_points:g}")
    t.step("Total", score)
    t.row_ids, t.row_count, t.sources = m.trace.row_ids, m.trace.row_count, m.trace.sources
    return ReadinessResult(score=score, band=_band(score), components=comps, top_tips=tips,
                           disclaimer="A self-assessment to prepare for lenders - not a credit score or a lending "
                                      "decision.", trace=t)


def readiness_inputs(ctx: Any) -> dict[str, Any]:
    """Helper used by the tool: uncategorised share + receivables outstanding from context data."""
    df = ctx.txns()
    share = float((df["category"] == "uncategorized").mean()) if not df.empty else 0.0
    inv = ctx.invoices()
    out = 0.0
    if not inv.empty:
        o = inv[(inv["kind"] == "receivable") & inv["status"].isin(["open", "partial"])]
        out = float((o["amount"] - o["amount_paid"]).sum())
    return {"uncategorized_share": share, "receivables_outstanding": out}
