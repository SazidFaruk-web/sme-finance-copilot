"""Tier-0 analysis tools and Tier-1 data-entry tools."""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from sme_copilot.tools import analysis as A
from sme_copilot.tools import repo
from sme_copilot.tools.categorize import all_category_names
from sme_copilot.tools.finance_math import amortization, cost_of_credit
from sme_copilot.tools.ingestion import store_parsed_entry
from sme_copilot.tools.nl_entry import ParsedEntry, parse_entry
from sme_copilot.tools.record_resolver import read_record, resolve_record
from sme_copilot.tools.stock import link_transaction
from sme_copilot.tools.textnorm import normalize
from sme_copilot.tools.trace import Trace, fmt

from .toolkit import PeriodArgs, ToolContext, tool


def _period(ctx: ToolContext, period: str):
    return A.resolve_period(period, ctx.as_of)


# ----------------------------------------------------------------------------- tier 0
@tool("get_financial_summary", "Income, expenses and net cash flow for a period, with category breakdown and "
      "monthly table.", PeriodArgs, 0, result_model=A.SummaryResult)
def get_financial_summary(ctx: ToolContext, a: PeriodArgs):
    s, e, label = _period(ctx, a.period)
    return A.income_expense_summary(ctx.txns(), s, e, label)


@tool("get_profitability", "Revenue, COGS, gross margin %, operating costs and net operating margin % for a "
      "period.", PeriodArgs, 0, result_model=A.ProfitabilityResult)
def get_profitability(ctx: ToolContext, a: PeriodArgs):
    s, e, label = _period(ctx, a.period)
    return A.profitability(ctx.txns(), s, e, label)


class BreakEvenArgs(BaseModel):
    months: int = Field(3, ge=1, le=12, description="Number of recent complete months to average")


@tool("get_break_even", "Break-even monthly sales, contribution margin and margin of safety.", BreakEvenArgs, 0,
      result_model=A.BreakEvenResult)
def get_break_even(ctx: ToolContext, a: BreakEvenArgs):
    return A.break_even(ctx.txns(), ctx.as_of, a.months)


class AgingArgs(BaseModel):
    kind: Literal["receivable", "payable"] = Field("receivable", description="receivable = customers owe you; "
                                                   "payable = you owe suppliers")


@tool("get_aging", "Receivables or payables aging buckets (not due, 1-30, 31-60, 61-90, 90+ days), overdue "
      "totals by customer/supplier, and DSO.", AgingArgs, 0, result_model=A.AgingResult)
def get_aging(ctx: ToolContext, a: AgingArgs):
    return A.aging(ctx.invoices(), ctx.as_of, a.kind, ctx.txns())


@tool("get_cost_drivers", "Top expense categories with share of total and change vs the previous period.",
      PeriodArgs, 0, result_model=A.CostDriversResult)
def get_cost_drivers(ctx: ToolContext, a: PeriodArgs):
    s, e, label = _period(ctx, a.period)
    return A.top_cost_drivers(ctx.txns(), s, e, label)


class NoArgs(BaseModel):
    pass


@tool("get_seasonality", "Monthly sales seasonality index, peaks/lows linked to Eid, Pohela Boishakh, harvest "
      "and export seasons, and upcoming festivals.", NoArgs, 0, result_model=A.SeasonalityResult)
def get_seasonality(ctx: ToolContext, a: NoArgs):
    return A.seasonality(ctx.txns(), ctx.as_of)


class ChangeArgs(PeriodArgs):
    period: str = "last_month"


@tool("explain_change", "Explain in plain language why income, costs and net cash flow changed versus the "
      "previous equal period (category and customer drivers).", ChangeArgs, 0, result_model=A.ExplainChangeResult)
def explain_change(ctx: ToolContext, a: ChangeArgs):
    s, e, label = _period(ctx, a.period)
    return A.explain_change(ctx.txns(), s, e, label, style=ctx.style)


class CashPosition(BaseModel):
    as_of: date
    balance: float
    opening_balance: float
    inflows_since_opening: float
    outflows_since_opening: float
    trace: Trace


@tool("get_cash_position", "Current cash / bank / wallet balance computed from the opening balance and all "
      "recorded transactions.", NoArgs, 0, result_model=CashPosition)
def get_cash_position(ctx: ToolContext, a: NoArgs):
    bal, br = repo.cash_position(ctx.business, ctx.txns(), ctx.as_of)
    t = Trace(formula="balance = opening balance + inflows - outflows since the opening date",
              period=f"{br['opening_date'] or 'start'} to {ctx.as_of}")
    t.step("Opening balance", br["opening"])
    t.step("Inflows", br["inflow"])
    t.step("Outflows", br["outflow"])
    t.step("Current balance", bal, f"{fmt(br['opening'])} + {fmt(br['inflow'])} - {fmt(br['outflow'])}")
    t.rows(br["rows"])
    return CashPosition(as_of=ctx.as_of, balance=bal, opening_balance=br["opening"],
                        inflows_since_opening=br["inflow"], outflows_since_opening=br["outflow"], trace=t)


class SearchArgs(BaseModel):
    text: str = Field("", description="Words to find in description or counterparty")
    category: str = Field("", description="Optional category filter")
    direction: Literal["", "in", "out"] = ""
    period: str = "last_3_months"
    flagged_only: bool = Field(False, description="Only anomalies / duplicates / suspicious rows")
    limit: int = Field(20, ge=1, le=100)

    @field_validator("period")
    @classmethod
    def _p(cls, v):
        return PeriodArgs(period=v).period


class SearchResult(BaseModel):
    count: int
    total_amount: float
    rows: list[dict]
    trace: Trace


@tool("search_transactions", "Find specific transactions (by text, category, direction, period, or flagged "
      "anomalies/duplicates).", SearchArgs, 0, result_model=SearchResult)
def search_transactions(ctx: ToolContext, a: SearchArgs):
    s, e, label = _period(ctx, a.period)
    from sme_copilot.tools.repo import load_transactions
    df = load_transactions(ctx.session, ctx.business.id, include_duplicates=a.flagged_only, end=ctx.as_of)
    df = df[(df["date"] >= str(s)) & (df["date"] <= str(e))] if not df.empty else df
    if a.text and not df.empty:
        q = a.text.lower()
        df = df[df["description"].str.lower().str.contains(q, regex=False) |
                df["counterparty"].str.lower().str.contains(q, regex=False)]
    if a.category and not df.empty:
        df = df[df["category"] == a.category]
    if a.direction and not df.empty:
        df = df[df["direction"] == a.direction]
    if a.flagged_only and not df.empty:
        df = df[df["flags"].apply(lambda f: bool(set(f) & {"anomaly", "duplicate", "injection_suspect"}))]
    total = float(df["amount"].sum()) if not df.empty else 0.0
    rows = [] if df.empty else [
        {"id": int(r.id), "date": r.date.date().isoformat(), "amount": float(r.amount), "direction": r.direction,
         "category": r.category, "counterparty": r.counterparty, "description": r.description[:120],
         "flags": list(r.flags), "source": r.source, "source_row": r.source_row}
        for r in df.sort_values("date", ascending=False).head(a.limit).itertuples()]
    t = Trace(formula="sum of matching rows", period=label)
    t.step("Matching rows", len(df))
    t.step("Total amount", round(total, 2))
    t.rows(df["id"].tolist() if not df.empty else [])
    return SearchResult(count=len(df), total_amount=round(total, 2), rows=rows, trace=t)


class LoanCalcArgs(BaseModel):
    principal: float = Field(..., gt=0, le=1e9, description="Loan amount in BDT")
    annual_rate_pct: float = Field(..., ge=0, le=60, description="Annual interest rate %, e.g. 12.5")
    months: int = Field(..., ge=1, le=240)
    method: Literal["reducing", "flat"] = "reducing"
    fee_pct: float = Field(0, ge=0, le=10, description="Upfront processing fee % of principal")


class LoanCalcResult(BaseModel):
    emi: float
    total_repayment: float
    total_interest: float
    fees: float
    total_cost_of_credit: float
    effective_apr_pct: float
    first_months: list[dict]
    trace: Trace


@tool("calculate_loan", "EMI, total repayment, total cost of credit and effective APR for a loan "
      "(reducing-balance or flat rate).", LoanCalcArgs, 0, result_model=LoanCalcResult, advisory=True)
def calculate_loan(ctx: ToolContext, a: LoanCalcArgs):
    c = cost_of_credit(a.principal, a.annual_rate_pct, a.months, method=a.method, fee_pct=a.fee_pct)
    t = Trace(formula="reducing EMI = P*r*(1+r)^n/((1+r)^n-1); flat EMI = (P + P*rate*n/12)/n")
    t.step("Principal", a.principal)
    t.step("Monthly rate r" if a.method == "reducing" else "Flat annual rate %",
           round(a.annual_rate_pct / 1200, 6) if a.method == "reducing" else a.annual_rate_pct)
    t.step("Months n", a.months)
    t.step("EMI", round(c.emi, 2))
    t.step("Total repayment", round(c.total_repayment, 2), f"{fmt(round(c.emi, 2))} x {a.months}")
    t.step("Total interest", round(c.total_interest, 2), f"{fmt(round(c.total_repayment, 2))} - {fmt(a.principal)}")
    t.step("Fees", round(c.fees, 2))
    t.step("Effective APR %", round(c.effective_apr_pct, 2), "rate equating instalments with cash actually received")
    sched = amortization(a.principal, a.annual_rate_pct, a.months)[:3] if a.method == "reducing" else []
    return LoanCalcResult(emi=round(c.emi, 2), total_repayment=round(c.total_repayment, 2),
                          total_interest=round(c.total_interest, 2), fees=round(c.fees, 2),
                          total_cost_of_credit=round(c.total_cost_of_credit, 2),
                          effective_apr_pct=round(c.effective_apr_pct, 2), first_months=sched, trace=t)


# ----------------------------------------------------------------------------- tier 1: data entry
class AddTxnArgs(BaseModel):
    text: str = Field("", max_length=300, description="The user's own words, e.g. 'sold 12 shirts for 6000 taka "
                                                      "cash' or 'dokan bhara 15000 dilam'")
    amount: float | None = Field(None, gt=0, le=1e9)
    direction: Literal["in", "out"] | None = None
    category: str | None = None
    txn_date: date | None = None
    counterparty: str | None = Field(None, max_length=120)
    channel: Literal["cash", "bank", "bkash", "nagad", "rocket", "card"] | None = None
    confirmed: bool = Field(False, description="True once the user accepted the preview of an uncertain reading")

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v and v not in all_category_names():
            raise ValueError(f"unknown category; use one of {all_category_names()}")
        return v


class AddTxnResult(BaseModel):
    recorded: bool
    transaction_id: int | None
    entry: dict
    duplicate_warning: str = ""
    anomaly_warning: str = ""
    missing: list[str] = []
    needs_confirm: bool = False
    preview: str = ""
    reason: str = ""
    manual_form: bool = False
    stock: dict | None = None
    credit: dict | None = None  # a credit sale (new customer bill) or a customer payment settling open bills


def _credit_entry(ctx: ToolContext, a: AddTxnArgs, e: ParsedEntry) -> AddTxnResult | None:
    """Credit sales become customer bills; payments from customers with open bills settle them (owner confirms)."""
    from sme_copilot.tools import credit_entry as ce

    money = lambda v: f"৳{v:,.0f}"  # noqa: E731
    try:
        pay = ce.customer_payment(ctx.session, ctx.business.id, a.text)
        sale = None if pay else ce.credit_sale(a.text)
    except ValueError:
        return AddTxnResult(recorded=False, transaction_id=None, entry=e.to_dict(), missing=["amount"],
                            manual_form=True, reason="Enter the payment or credit-sale amount separately; more than one amount was found.")
    if pay:
        name, amount, invs = pay
        owed = sum(float(i.amount) - float(i.amount_paid or 0) for i in invs)
        info = {"kind": "payment", "customer": name, "amount": amount, "owed_before": round(owed, 2),
                "bills": [i.invoice_no for i in invs]}
        if not a.confirmed:
            return AddTxnResult(recorded=False, transaction_id=None, entry=e.to_dict(), needs_confirm=True, credit=info,
                                preview=f"Payment from {name}: {money(amount)}. It settles their open bills "
                                        f"(they owed {money(owed)}). Save?", reason="customer payment")
        t, applied = ce.apply_payment(ctx.session, ctx.business.id, invs, amount, date.fromisoformat(e.txn_date), e.channel, ctx.user.username)
        ctx.session.commit()
        return AddTxnResult(recorded=True, transaction_id=t.id, entry={**e.to_dict(), "amount": amount, "direction": "in",
                            "category": "sales", "counterparty": name}, credit={**info, "applied": applied,
                            "still_owed": round(owed - amount, 2)})
    if sale:
        name, amount = sale
        info = {"kind": "credit_sale", "customer": name, "amount": amount, "due_in_days": ce.CREDIT_DAYS}
        if not a.confirmed:
            return AddTxnResult(recorded=False, transaction_id=None, entry=e.to_dict(), needs_confirm=True, credit=info,
                                preview=f"Credit sale: {name} will owe you {money(amount)}, due in {ce.CREDIT_DAYS} days. "
                                        f"No cash is recorded until they pay. Save?", reason="credit sale")
        inv = ce.record_credit_sale(ctx.session, ctx.business.id, name, amount, date.fromisoformat(e.txn_date), a.text)
        ctx.session.commit()
        return AddTxnResult(recorded=True, transaction_id=None, entry={**e.to_dict(), "amount": amount, "counterparty": name,
                                                                      "direction": None, "category": "credit_sale"},
                            credit={**info, "invoice_no": inv.invoice_no, "due_date": inv.due_date.isoformat()})
    return None


@tool("add_transaction", "Record a sale, expense or payment from a quick natural-language entry (English, "
      "Bangla or Banglish). Pass the user's words in 'text'; optional fields override the parser.",
      AddTxnArgs, 1, category="data", result_model=AddTxnResult, mutates=True)
def add_transaction(ctx: ToolContext, a: AddTxnArgs):
    e: ParsedEntry = parse_entry(a.text, ctx.as_of) if a.text else ParsedEntry(
        amount=None, direction=None, category="uncategorized", channel="cash", txn_date=ctx.as_of.isoformat())
    link = None
    if a.text and a.amount is None and a.direction is None:
        credit = _credit_entry(ctx, a, e)
        if credit is not None:
            return credit
    if a.text and a.amount is None and a.direction is None:
        # Free text: extraction (regex fast path or LLM) + Python-computed amount and sign.
        ex, _src = read_record(a.text)
        if ex is None:
            if len(re.findall(r"\d+", normalize(a.text))) != 1:  # legacy parser is only safe with a single number
                return AddTxnResult(recorded=False, transaction_id=None, entry=e.to_dict(), manual_form=True,
                                    preview="Could not read this, please use the form")
        else:
            r = resolve_record(ex)
            if r["needs_confirm"] and not a.confirmed:
                return AddTxnResult(recorded=False, transaction_id=None, entry=e.to_dict(), needs_confirm=True,
                                    preview=r["preview"], reason=r["reason"])
            if r["amount"] is None or r["amount"] <= 0:
                return AddTxnResult(recorded=False, transaction_id=None, entry=e.to_dict(), manual_form=True,
                                    reason=r["reason"], preview="Could not read this, please use the form")
            link = (r["type"], r["item"], r["quantity"])
            e.amount, e.direction, e.category = r["amount"], r["direction"], r["category"]
            e.quantity, e.item = r["quantity"], r["item"] or e.item
            e.counterparty = r["counterparty"] or e.counterparty
            if ex.get("payment_method") in ("cash", "bkash", "bank"):
                e.channel = ex["payment_method"]
    if a.amount is not None:
        e.amount = a.amount
    if a.direction:
        e.direction = a.direction
    if a.category:
        e.category = a.category
    if a.txn_date:
        if a.txn_date > ctx.as_of:
            raise ValueError("transaction date cannot be in the future")
        e.txn_date = a.txn_date.isoformat()
    if a.counterparty is not None:
        e.counterparty = a.counterparty
    if a.channel:
        e.channel = a.channel
    if not e.description:
        e.description = a.text or f"{e.direction} {e.amount}"
    e.missing = [m for m in ("amount", "direction") if getattr(e, m) is None]
    if e.missing:
        return AddTxnResult(recorded=False, transaction_id=None, entry=e.to_dict(), missing=e.missing)
    if e.category == "uncategorized" and e.direction == "in":
        e.category = "sales"
    rep = store_parsed_entry(ctx.session, ctx.business.id, e, source="nl" if ctx.origin == "agent" else "manual")
    tid = None
    from sqlalchemy import select

    from sme_copilot.models import Transaction
    last = ctx.session.scalar(select(Transaction).where(Transaction.business_id == ctx.business.id)
                              .order_by(Transaction.id.desc()).limit(1))
    tid = last.id if last else None
    stock = link_transaction(ctx.session, ctx.business.id, tid, *link) if link and rep.imported == 1 and tid else None
    return AddTxnResult(recorded=rep.imported == 1, transaction_id=tid, entry=e.to_dict(), stock=stock,
                        duplicate_warning=rep.duplicates[0]["reason"] if rep.duplicates else "",
                        anomaly_warning=rep.anomalies[0]["reason"] if rep.anomalies else "")
