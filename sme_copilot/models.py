"""ORM models.

Money is stored as NUMERIC(14,2) and handled as float rounded to 2 dp in the finance tools
(SME scale; see ASSUMPTIONS.md). Sensitive identifiers use ``EncryptedString``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sme_copilot.db import Base
from sme_copilot.security.crypto import EncryptedString


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


Money = Numeric(14, 2, asdecimal=False)


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(80), default="trading")
    district: Mapped[str] = mapped_column(String(80), default="Dhaka")
    owner_name: Mapped[str] = mapped_column(String(120), default="")
    established_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    trade_license_no: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    tin: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    has_trade_license: Mapped[bool] = mapped_column(Boolean, default=False)
    has_tin: Mapped[bool] = mapped_column(Boolean, default=False)
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    has_bank_account: Mapped[bool] = mapped_column(Boolean, default=True)
    women_led: Mapped[bool] = mapped_column(Boolean, default=False)
    collateral_value: Mapped[float] = mapped_column(Money, default=0)
    existing_monthly_debt_service: Mapped[float] = mapped_column(Money, default=0)
    opening_cash_balance: Mapped[float] = mapped_column(Money, default=0)
    opening_balance_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    low_balance_threshold: Mapped[float] = mapped_column(Money, default=50_000)
    prefs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="business")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(80), unique=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | accountant | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    business: Mapped[Business] = relationship(back_populates="users")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of the bearer token
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(30))
    file_sha256: Mapped[str] = mapped_column(String(64))
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    anomalies: Mapped[int] = mapped_column(Integer, default=0)
    injection_flags: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_txn_business_date", "business_id", "txn_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    txn_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Money)  # always positive
    direction: Mapped[str] = mapped_column(String(3))  # in | out
    category: Mapped[str] = mapped_column(String(40), default="uncategorized")
    counterparty: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(20), default="cash")  # cash|bank|bkash|nagad|rocket|card
    account_ref: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    reference: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    item: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_reason: Mapped[str] = mapped_column(String(300), default="")
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    categorized_by: Mapped[str] = mapped_column(String(10), default="rule")  # rule|llm|user|file
    category_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(12))  # receivable | payable
    invoice_no: Mapped[str] = mapped_column(String(60), default="")
    counterparty: Mapped[str] = mapped_column(String(200))
    counterparty_phone: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    amount: Mapped[float] = mapped_column(Money)
    amount_paid: Mapped[float] = mapped_column(Money, default=0)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|partial|paid|written_off
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Obligation(Base):
    """Recurring or scheduled outflows: rent, salary, loan EMI, VAT, utilities."""
    __tablename__ = "obligations"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Money)
    frequency: Mapped[str] = mapped_column(String(12), default="monthly")  # monthly|quarterly|yearly|once
    day_of_month: Mapped[int] = mapped_column(Integer, default=1)
    next_due: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("business_id", "dedupe_key", name="uq_alert_dedupe"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info|warning|critical
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(14), default="open")  # open|acknowledged|dismissed|scheduled
    dedupe_key: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(20), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    counterparty: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Money, default=0)
    remind_on: Mapped[date] = mapped_column(Date)
    channel: Mapped[str] = mapped_column(String(12), default="sms")
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="scheduled")  # scheduled|sent_simulated|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    recipient: Mapped[str] = mapped_column(String(200), default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    tone: Mapped[str] = mapped_column(String(20), default="polite")
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SandboxAccount(Base):
    __tablename__ = "sandbox_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80), default="Sandbox Operating Account")
    account_no: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    balance: Mapped[float] = mapped_column(Money, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="BDT")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SandboxTransfer(Base):
    __tablename__ = "sandbox_transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("sandbox_accounts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20), default="transfer")  # transfer | invoice_payment
    recipient_name: Mapped[str] = mapped_column(String(200))
    recipient_account: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    amount: Mapped[float] = mapped_column(Money)
    purpose: Mapped[str] = mapped_column(String(300), default="")
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|executed|rejected|expired|blocked
    pending_action_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    balance_after: Mapped[float | None] = mapped_column(Money, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PendingAction(Base):
    """Human-in-the-loop queue: a Tier-2 tool call waits here until the user confirms."""
    __tablename__ = "pending_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tool: Mapped[str] = mapped_column(String(60))
    args: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tier: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    amount: Mapped[float] = mapped_column(Money, default=0)
    recipient: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|confirmed|rejected|expired|failed
    origin: Mapped[str] = mapped_column(String(12), default="agent")
    request_id: Mapped[str] = mapped_column(String(40), default="")
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(80), default="")


class AuditEvent(Base):
    """Append-only, hash-chained log of every agent decision and action.

    ``hash = sha256(prev_hash + canonical_json(event))``; SQLite triggers reject UPDATE/DELETE.
    Inputs/results are PII-masked before storage, so the log can be kept even after a data
    deletion request (see SECURITY_ASSESSMENT.md).
    """
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    business_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # no FK: survives deletion
    actor: Mapped[str] = mapped_column(String(80))
    actor_role: Mapped[str] = mapped_column(String(20), default="")
    event_type: Mapped[str] = mapped_column(String(30))  # agent_decision|tool_call|operation|permission_denied|auth|data|security
    action: Mapped[str] = mapped_column(String(80))
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confirmation_status: Mapped[str] = mapped_column(String(20), default="not_required")
    request_id: Mapped[str] = mapped_column(String(40), default="")
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (Index("ix_item_business", "business_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    unit: Mapped[str] = mapped_column(String(20), default="pcs")
    opening_qty: Mapped[float] = mapped_column(Float, default=0)
    reorder_level: Mapped[float] = mapped_column(Float, default=0)
    cost_price: Mapped[float] = mapped_column(Money, default=0)


class StockMovement(Base):
    """Append-only: current stock = item.opening_qty + SUM(qty_change). Corrections are new (reversal) rows."""
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_move_item", "item_id"), Index("ix_move_txn", "transaction_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    qty_change: Mapped[float] = mapped_column(Float)  # signed
    reason: Mapped[str] = mapped_column(String(40))  # sale|sale_return|purchase|purchase_return|adjust|reversal:<reason>
    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # no FK: survives txn deletion
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
