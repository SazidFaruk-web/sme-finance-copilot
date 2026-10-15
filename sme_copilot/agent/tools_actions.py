"""Action-layer tools: Tier 1 (drafts, reminders, reports), Tier 2 (sandbox money), Tier 3 (blocked).

Every handler here writes to the database and is recorded in the operation log (audit events
of type "operation") by the executor, with inputs, result and confirmation status.
"""
from __future__ import annotations

from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from sme_copilot.config import get_settings
from sme_copilot.financing_catalog.loader import load_catalog
from sme_copilot.financing_catalog.matcher import match
from sme_copilot.financing_catalog.readiness import readiness, readiness_inputs
from sme_copilot.forecasting.alerts import compliance_rules
from sme_copilot.forecasting.forecast import build_inputs, project
from sme_copilot.models import Draft, Invoice, Obligation, Reminder, Report, SandboxAccount, SandboxTransfer, Transaction, utcnow
from sme_copilot.sandbox import messages
from sme_copilot.sandbox.pdf_report import build_pdf
from sme_copilot.security.injection import neutralize
from sme_copilot.security.pii import mask_account
from sme_copilot.tools import repo
from sme_copilot.tools.analysis import aging, business_metrics, monthly_table, profitability, resolve_period
from sme_copilot.tools.categorize import categorize
from sme_copilot.tools.money import format_bdt
from sme_copilot.tools.trace import Trace
from sme_copilot.tools.textnorm import normalize

from .toolkit import ToolContext, tool


# ----------------------------------------------------------------------------- helpers
def find_invoice(ctx: ToolContext, *, invoice_id: int | None, counterparty: str | None, kind: str) -> Invoice:
    q = select(Invoice).where(Invoice.business_id == ctx.business.id, Invoice.kind == kind,
                              Invoice.status.in_(["open", "partial"]))
    if invoice_id:
        inv = ctx.session.get(Invoice, invoice_id)
        if inv is None or inv.business_id != ctx.business.id or inv.kind != kind:
            raise LookupError(f"{kind} invoice {invoice_id} not found")
        if inv.status not in ("open", "partial"):
            raise ValueError(f"invoice {inv.invoice_no or inv.id} is already {inv.status}")
        return inv
    rows = list(ctx.session.scalars(q))
    if counterparty:
        target = normalize(counterparty)
        scored = [(max(SequenceMatcher(None, target, normalize(i.counterparty)).ratio(),
                       1.0 if target and target in normalize(i.counterparty) else 0.0), i) for i in rows]
        scored = [s for s in scored if s[0] >= 0.6]
        if not scored:
            # Names may arrive in another script or spelling ("করিম নিট" vs "Karim Knit"): list the real ones so
            # the model can retry with the exact record name. They are uploaded data, so neutralise them.
            names = sorted({neutralize(i.counterparty) for i in rows if i.counterparty})[:15]
            raise LookupError(f"no open {kind} invoice found for '{counterparty}'. Open {kind} invoices exist for: "
                              f"{', '.join(names) or 'nobody'}. If one of these is meant (e.g. the same name in "
                              "another script or spelling), call again with that exact name.")
        best = max(s[0] for s in scored)
        rows = [i for sc, i in scored if sc == best]
    if not rows:
        raise LookupError(f"no open {kind} invoices")
    return min(rows, key=lambda i: i.due_date)  # most overdue first


def _outstanding(inv: Invoice) -> float:
    return round(float(inv.amount) - float(inv.amount_paid or 0), 2)


class InvoiceRef(BaseModel):
    invoice_id: int | None = Field(None, description="Invoice id; or give counterparty")
    counterparty: str | None = Field(None, max_length=120, description="Customer name (fuzzy match); empty = most overdue")


# ----------------------------------------------------------------------------- tier 1
class ReminderArgs(InvoiceRef):
    remind_on: date | None = Field(None, description="Date to send; default tomorrow")
    channel: Literal["sms", "whatsapp", "email"] = "sms"
    language: Literal["en", "bn"] = "en"
    amount: float = Field(0, ge=0, le=1e10, description="Filled automatically")
    recipient_name: str = Field("", max_length=200, description="Filled automatically")
    preview: str = Field("", max_length=1000, description="Filled automatically")


def _prepare_reminder(ctx: ToolContext, a: ReminderArgs) -> ReminderArgs:
    """Resolve the invoice and build the exact message so the confirm dialog can show it (never model text)."""
    inv = find_invoice(ctx, invoice_id=a.invoice_id, counterparty=a.counterparty, kind="receivable")
    msg = messages.sms(a.language, biz=ctx.business.name, inv=inv.invoice_no or f"#{inv.id}", amount=_outstanding(inv),
                       due=inv.due_date, style=ctx.style)
    return a.model_copy(update={"invoice_id": inv.id, "amount": _outstanding(inv), "recipient_name": inv.counterparty,
                                "preview": msg})


class ReminderResult(BaseModel):
    reminder_id: int
    invoice_id: int
    invoice_no: str
    counterparty: str
    amount: float
    days_overdue: int
    remind_on: date
    channel: str
    to: str
    message: str
    status: str
    note: str


@tool("create_payment_reminder", "Schedule a payment reminder (SMS/WhatsApp/email, simulated outbox) to a customer "
      "for an open invoice, with a ready message.", ReminderArgs, 1, category="action", result_model=ReminderResult,
      prepare=_prepare_reminder, always_confirm=True, amount_field="amount", recipient_field="recipient_name",
      summarize=lambda a: f"Queue a {a.channel} reminder to {a.recipient_name} for {format_bdt(a.amount)} "
                          f"(simulated outbox, nothing is sent to a real phone)")
def create_payment_reminder(ctx: ToolContext, a: ReminderArgs):
    inv = find_invoice(ctx, invoice_id=a.invoice_id, counterparty=a.counterparty, kind="receivable")
    when = a.remind_on or ctx.as_of + timedelta(days=1)
    if when < ctx.as_of:
        raise ValueError("reminder date is in the past")
    amt = _outstanding(inv)
    msg = messages.sms(a.language, biz=ctx.business.name, inv=inv.invoice_no or f"#{inv.id}", amount=amt,
                       due=inv.due_date, style=ctx.style)
    r = Reminder(business_id=ctx.business.id, invoice_id=inv.id, counterparty=inv.counterparty, amount=amt,
                 remind_on=when, channel=a.channel, message=msg, status="scheduled")
    ctx.session.add(r)
    ctx.session.flush()
    return ReminderResult(reminder_id=r.id, invoice_id=inv.id, invoice_no=inv.invoice_no, counterparty=inv.counterparty,
                          amount=amt, days_overdue=max(0, (ctx.as_of - inv.due_date).days), remind_on=when,
                          channel=a.channel, to=mask_account(inv.counterparty_phone) or "(no phone on file)",
                          message=msg, status="scheduled",
                          note="Sandbox: the message is queued in the simulated outbox, not sent to a real phone.")


class FollowupArgs(InvoiceRef):
    tone: Literal["polite", "firm", "final"] = "polite"
    language: Literal["en", "bn"] = "en"


class FollowupResult(BaseModel):
    draft_id: int
    invoice_id: int
    invoice_no: str
    counterparty: str
    amount: float
    days_overdue: int
    subject: str
    body: str
    status: str


@tool("draft_invoice_followup", "Draft a follow-up message (email/letter) for an overdue invoice in English or "
      "Bangla, polite/firm/final tone. Saved as a draft for the owner to review.", FollowupArgs, 1, category="action",
      result_model=FollowupResult)
def draft_invoice_followup(ctx: ToolContext, a: FollowupArgs):
    inv = find_invoice(ctx, invoice_id=a.invoice_id, counterparty=a.counterparty, kind="receivable")
    amt = _outstanding(inv)
    subj, body = messages.followup(a.language, a.tone, party=inv.counterparty, inv=inv.invoice_no or f"#{inv.id}",
                                   amount=amt, due=inv.due_date, as_of=ctx.as_of, biz=ctx.business.name,
                                   pay_by=ctx.as_of + timedelta(days=7 if a.tone == "polite" else 3), style=ctx.style)
    d = Draft(business_id=ctx.business.id, kind="invoice_followup", invoice_id=inv.id, recipient=inv.counterparty,
              language=a.language, tone=a.tone, subject=subj, body=body, status="draft")
    ctx.session.add(d)
    ctx.session.flush()
    return FollowupResult(draft_id=d.id, invoice_id=inv.id, invoice_no=inv.invoice_no, counterparty=inv.counterparty,
                          amount=amt, days_overdue=max(0, (ctx.as_of - inv.due_date).days), subject=subj, body=body,
                          status="draft")


class ReportArgs(BaseModel):
    amount: float | None = Field(None, gt=0, le=1e9, description="Loan amount to prepare for (optional)")
    purpose: Literal["working_capital", "inventory", "equipment", "expansion", "seasonal", "receivables_gap"] = \
        "working_capital"


class ReportResult(BaseModel):
    report_id: int
    filename: str
    download_url: str
    sha256: str
    readiness_score: float
    pages_note: str


@tool("generate_loan_report", "Generate a loan-readiness PDF report for a bank (KPIs, forecast, readiness score, "
      "financing options).", ReportArgs, 1,
      category="action", result_model=ReportResult, advisory=True,
      summarize=lambda a: "Create a loan-readiness PDF with your sales, costs, cash forecast and readiness score"
                          + (f" for a {format_bdt(a.amount)} loan" if a.amount else "")
                          + ". It stays on this computer until you download and share it.")
def generate_loan_report(ctx: ToolContext, a: ReportArgs):
    txns, inv = ctx.txns(), ctx.invoices()
    s6, e6, l6 = resolve_period("last_6_months", ctx.as_of)
    prof = profitability(txns, s6, e6, l6)
    s12, _, _ = resolve_period("last_12_months", ctx.as_of)
    monthly = monthly_table(txns[txns["date"] >= str(s12)]) if not txns.empty else []
    fc = project(build_inputs(txns, inv, repo.load_obligations(ctx.session, ctx.business.id), ctx.business,
                              ctx.as_of, 90))
    ar = aging(inv, ctx.as_of, "receivable") if not inv.empty else None
    m = business_metrics(txns, inv, ctx.business, ctx.as_of)
    rd = readiness(m, **readiness_inputs(ctx), style=ctx.style)
    mt = match(m, ctx.business, amount=a.amount, purpose=a.purpose, style=ctx.style)
    rep = Report(business_id=ctx.business.id, kind="loan_readiness", filename="", sha256="",
                 params={"amount": a.amount, "purpose": a.purpose, "as_of": ctx.as_of.isoformat()})
    ctx.session.add(rep)
    ctx.session.flush()
    fname = f"loan_readiness_b{ctx.business.id}_{rep.id}_{ctx.as_of.isoformat()}.pdf"
    path = get_settings().reports_dir / fname
    sha = build_pdf(path, business=ctx.business, as_of=ctx.as_of, amount=a.amount, purpose=a.purpose, profit=prof,
                    monthly=monthly, forecast=fc, aging=ar, readiness=rd, matches=mt)
    rep.filename, rep.sha256 = fname, sha
    return ReportResult(report_id=rep.id, filename=fname, download_url=f"/api/reports/{rep.id}/download", sha256=sha,
                        readiness_score=rd.score, pages_note="Includes disclaimer; financing terms illustrative.")


class ChecklistArgs(BaseModel):
    product_id: str | None = Field(None, description="Catalog product id; default = best current match")
    amount: float | None = Field(None, gt=0, le=1e9)


class ChecklistItem(BaseModel):
    document: str
    status: Literal["have", "missing", "can_generate", "to_prepare"]
    how: str


class ChecklistResult(BaseModel):
    product_id: str
    product_name: str
    verify_label: str
    items: list[ChecklistItem]
    ready_count: int
    total: int
    next_steps: list[str]
    draft_id: int


HOW = {"have": "Already on file - bring a copy.", "missing": "Not on file - obtain before applying.",
       "can_generate": "The copilot can produce this from your records (loan-readiness report).",
       "to_prepare": "Prepare and bring the original."}


@tool("prepare_loan_checklist", "Prepare a loan application checklist for a financing product: documents you have, "
      "documents missing, and ones the copilot can generate.", ChecklistArgs, 1, category="action",
      result_model=ChecklistResult)
def prepare_loan_checklist(ctx: ToolContext, a: ChecklistArgs):
    cat = load_catalog()
    if a.product_id:
        p = cat.get(a.product_id)
    else:
        m = business_metrics(ctx.txns(), ctx.invoices(), ctx.business, ctx.as_of)
        res = match(m, ctx.business, amount=a.amount, style=ctx.style)
        if not res.recommendations:
            raise ValueError("no eligible financing option right now; ask for the loan-readiness score for tips")
        p = cat.get(res.recommendations[0].product_id)
    from sme_copilot.financing_catalog.matcher import _docs
    items = [ChecklistItem(document=d["label"], status=d["status"], how=HOW[d["status"]]) for d in
             _docs(p, ctx.business, cat)]
    ready = sum(1 for i in items if i.status in ("have", "can_generate"))
    steps = [f"Obtain: {i.document}" for i in items if i.status == "missing"]
    steps += ["Generate the loan-readiness report (PDF) to attach", f"Confirm current terms with the lender "
              f"({p.verify_label.lower()})"]
    body = "\n".join(f"[{'x' if i.status in ('have', 'can_generate') else ' '}] {i.document} - {i.how}" for i in items)
    d = Draft(business_id=ctx.business.id, kind="loan_checklist", recipient=p.name, language="en", tone="",
              subject=f"Loan checklist: {p.name}", body=body, status="draft")
    ctx.session.add(d)
    ctx.session.flush()
    return ChecklistResult(product_id=p.id, product_name=p.name, verify_label=p.verify_label, items=items,
                           ready_count=ready, total=len(items), next_steps=steps, draft_id=d.id)


class ObligationArgs(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    category: Literal["rent", "salary", "loan_repayment", "utilities", "tax_vat", "other"] = "rent"
    amount: float = Field(..., gt=0, le=1e8)
    day_of_month: int = Field(1, ge=1, le=28)
    frequency: Literal["monthly", "quarterly", "yearly", "once"] = "monthly"


class ObligationResult(BaseModel):
    obligation_id: int
    name: str
    amount: float
    next_due: date


@tool("add_obligation", "Record a recurring payment (rent, salary, loan EMI, VAT, utilities) so forecasts and alerts "
      "include it.", ObligationArgs, 1, category="action", result_model=ObligationResult, mutates=True)
def add_obligation(ctx: ToolContext, a: ObligationArgs):
    from sme_copilot.tools.analysis import add_months
    nd = ctx.as_of.replace(day=a.day_of_month)
    if nd <= ctx.as_of:
        nd = add_months(nd, 1)
    o = Obligation(business_id=ctx.business.id, name=a.name, category=a.category, amount=a.amount,
                   frequency=a.frequency, day_of_month=a.day_of_month, next_due=nd, source="user")
    ctx.session.add(o)
    ctx.session.flush()
    return ObligationResult(obligation_id=o.id, name=o.name, amount=a.amount, next_due=nd)


# ----------------------------------------------------------------------------- tier 2: sandbox money
class TransferArgs(BaseModel):
    recipient_name: str = Field(..., min_length=2, max_length=120)
    recipient_account: str = Field("", max_length=40, description="Wallet/bank number (sandbox)")
    amount: float = Field(..., gt=0, le=1e9)
    purpose: str = Field("", max_length=200)

    @model_validator(mode="after")
    def _clean(self):
        if self.recipient_name.strip().lower() in ("unknown recipient", "unknown", ""):
            raise ValueError("recipient_name is required (who should receive the money?)")
        return self


class TransferResult(BaseModel):
    transfer_id: int
    status: str
    recipient_name: str
    recipient_account: str
    amount: float
    balance_before: float
    balance_after: float
    executed_at: str
    transaction_id: int | None
    sandbox: bool = True


def _execute_transfer(ctx: ToolContext, *, recipient: str, account: str, amount: float, purpose: str,
                      kind: str, invoice_id: int | None = None) -> TransferResult:
    acct = ctx.session.scalar(select(SandboxAccount).where(SandboxAccount.business_id == ctx.business.id))
    if acct is None:
        raise LookupError("no sandbox account for this business")
    if ctx.origin != "confirmation":
        # Defence in depth: tier-2 handlers only ever run via confirm_pending().
        raise PermissionError("sandbox money movement requires explicit confirmation")
    before = float(acct.balance)
    if before < amount:
        raise ValueError("insufficient sandbox balance")
    acct.balance = round(before - amount, 2)
    now = utcnow()
    t = SandboxTransfer(business_id=ctx.business.id, account_id=acct.id, kind=kind, recipient_name=recipient,
                        recipient_account=account or None, amount=amount, purpose=purpose, invoice_id=invoice_id,
                        status="executed", pending_action_id=ctx.pending_action_id, balance_after=acct.balance,
                        executed_at=now)
    ctx.session.add(t)
    cat = "inventory" if kind == "invoice_payment" else categorize(f"{purpose} {recipient}", "out").category
    txn = Transaction(business_id=ctx.business.id, txn_date=ctx.as_of, amount=amount, direction="out",
                      category=cat if cat != "uncategorized" else "misc_expense", counterparty=recipient,
                      description=f"[sandbox] {purpose or kind}", channel="bank", account_ref=account or None,
                      reference=f"SBX-{ctx.pending_action_id}", source="sandbox", flags=["sandbox"])
    ctx.session.add(txn)
    ctx.session.flush()
    ctx.invalidate()
    return TransferResult(transfer_id=t.id, status="executed", recipient_name=recipient,
                          recipient_account=mask_account(account), amount=amount, balance_before=before,
                          balance_after=float(acct.balance), executed_at=now.isoformat(timespec="seconds"),
                          transaction_id=txn.id)


def _transfer_summary(a: TransferArgs) -> str:
    acct = f" ({mask_account(a.recipient_account)})" if a.recipient_account else ""
    return f"Send {format_bdt(a.amount)} to {a.recipient_name}{acct} from the SANDBOX account" + \
        (f" for: {a.purpose}" if a.purpose else "")


@tool("sandbox_transfer", "Prepare a simulated money transfer from the sandbox account to a recipient.", TransferArgs, 2,
      category="money", result_model=TransferResult, amount_field="amount", recipient_field="recipient_name",
      summarize=_transfer_summary, mutates=True)
def sandbox_transfer(ctx: ToolContext, a: TransferArgs):
    return _execute_transfer(ctx, recipient=a.recipient_name, account=a.recipient_account, amount=a.amount,
                             purpose=a.purpose, kind="transfer")


class PayInvoiceArgs(BaseModel):
    invoice_id: int | None = Field(None, description="Payable (supplier) invoice id; or give counterparty")
    counterparty: str | None = Field(None, max_length=120, description="Supplier name (fuzzy match)")
    amount: float = Field(0, ge=0, description="Filled automatically with the outstanding amount")
    recipient_name: str = Field("", description="Filled automatically with the supplier name")


def _prepare_payment(ctx: ToolContext, a: PayInvoiceArgs) -> PayInvoiceArgs:
    """Derive amount and recipient from the invoice so limits are checked on the real figure."""
    inv = find_invoice(ctx, invoice_id=a.invoice_id, counterparty=a.counterparty, kind="payable")
    return a.model_copy(update={"invoice_id": inv.id, "amount": _outstanding(inv), "recipient_name": inv.counterparty})


@tool("pay_supplier_invoice", "Prepare a simulated sandbox payment of a supplier (payable) invoice.", PayInvoiceArgs, 2,
      category="money", result_model=TransferResult,
      amount_field="amount", recipient_field="recipient_name", mutates=True, prepare=_prepare_payment,
      summarize=lambda a: f"Pay {a.recipient_name} invoice #{a.invoice_id} ({format_bdt(a.amount)}) from the SANDBOX "
                          f"account")
def pay_supplier_invoice(ctx: ToolContext, a: PayInvoiceArgs):
    inv = find_invoice(ctx, invoice_id=a.invoice_id, counterparty=None, kind="payable")
    amt = _outstanding(inv)
    if abs(amt - a.amount) > 0.005:
        raise ValueError("invoice amount changed since the request; create a new request")
    res = _execute_transfer(ctx, recipient=inv.counterparty, account=inv.counterparty_phone or "", amount=amt,
                            purpose=f"Invoice {inv.invoice_no or inv.id}", kind="invoice_payment", invoice_id=inv.id)
    inv.amount_paid, inv.status, inv.paid_date = float(inv.amount), "paid", ctx.as_of
    return res


# ----------------------------------------------------------------------------- compliance (tier 0)
class ComplianceArgs(BaseModel):
    topic: Literal["vat", "tin", "trade_license", "kyc_aml", "finance", "all"] = "all"


class ComplianceResult(BaseModel):
    topic: str
    rules: list[dict[str, Any]]
    disclaimer: str


@tool("compliance_info", "Bangladesh compliance info and due dates: VAT, e-TIN/income tax, trade licence, KYC/AML, "
      "central-bank SME schemes.", ComplianceArgs, 0,
      category="analysis", result_model=ComplianceResult, advisory=True)
def compliance_info(ctx: ToolContext, a: ComplianceArgs):
    cfg = compliance_rules()
    rules = [r for r in cfg.get("rules", []) if a.topic == "all" or r.get("topic") == a.topic]
    out = []
    for r in rules:
        applies = all(bool(getattr(ctx.business, k, False)) == bool(v) for k, v in (r.get("applies_if") or {}).items())
        out.append({"id": r["id"], "title": r["title"], "summary": " ".join(r["summary"].split()),
                    "applies_to_you": applies, "verified": r.get("verified", False),
                    "verify_label": "Verified" if r.get("verified") else "Configured - verify with the authority",
                    "source_url": r.get("source_url"), "last_verified_date": r.get("last_verified_date")})
    return ComplianceResult(topic=a.topic, rules=out, disclaimer=" ".join(cfg.get("disclaimer", "").split()))


# ----------------------------------------------------------------------------- tier 3: blocked
# Registered on purpose: if a manipulated model (e.g. via prompt injection in an uploaded file)
# tries any of these, the permission layer refuses and the attempt lands in the audit log.
class RealTransferArgs(BaseModel):
    recipient: str = ""
    amount: float = 0
    account_number: str = ""


def _never(ctx: ToolContext, a):  # pragma: no cover - permission layer refuses before this runs
    raise RuntimeError("blocked tool executed - permission layer bypassed")


tool("execute_real_bank_transfer", "Move REAL money from the user's bank or mobile wallet. BLOCKED: this copilot "
     "only operates a sandbox account.", RealTransferArgs, 3, category="blocked")(_never)


class LimitArgs(BaseModel):
    per_transaction_limit: float = 0
    daily_cap: float = 0


tool("change_transaction_limits", "Raise or remove sandbox transaction limits. BLOCKED for the agent; limits are "
     "set by the operator via environment configuration.", LimitArgs, 3, category="blocked")(_never)


class AuditDeleteArgs(BaseModel):
    reason: str = ""


tool("delete_audit_log", "Delete or edit audit log entries. BLOCKED: the audit log is append-only.",
     AuditDeleteArgs, 3, category="blocked")(_never)


class ExportArgs(BaseModel):
    destination: str = Field("", description="email or URL")


tool("export_all_data_externally", "Send business or customer data to an external address. BLOCKED: "
     "data never leaves the app through the agent.", ExportArgs, 3, category="blocked")(_never)
