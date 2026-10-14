"""Permission tiers, enforced in code (never in the prompt).

Tier 0  read-only analysis                     viewer, accountant, owner
Tier 1  drafts, reminders, data entry, reports accountant, owner
Tier 2  sandbox money movement                 owner only + explicit human confirmation,
                                               per-transaction limit, daily cap, balance check
Tier 3  blocked                                nobody (attempts are refused and audited)

``authorize`` is the single choke point that every tool call goes through, whether the call
came from the LLM, the rules engine, or a UI button (POST /api/tools/{name}).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sme_copilot.config import Settings, get_settings
from sme_copilot.models import PendingAction, SandboxAccount, SandboxTransfer, User, utcnow

TIER_NAMES = {
    0: "Tier 0 - read-only analysis",
    1: "Tier 1 - drafts, reminders and data entry",
    2: "Tier 2 - sandbox money movement (explicit confirmation required)",
    3: "Tier 3 - blocked",
}
ROLE_MAX_TIER = {"viewer": 0, "accountant": 1, "owner": 2}
BD_OFFSET = timezone(timedelta(hours=6))  # Asia/Dhaka, no DST


def local_today() -> date:
    return datetime.now(BD_OFFSET).date()


def local_day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day, tzinfo=BD_OFFSET).astimezone(timezone.utc).replace(tzinfo=None)
    return start, start + timedelta(days=1)


@dataclass
class Decision:
    allowed: bool
    requires_confirmation: bool
    tier: int
    code: str  # ok | role | blocked | limit_txn | limit_daily | insufficient_funds | invalid_amount
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def pending_reserved(session: Session, business_id: int, *, exclude_pending_id: int | None = None) -> float:
    """Money already promised to unexpired pending Tier-2 requests."""
    q = select(func.coalesce(func.sum(PendingAction.amount), 0)).where(
        PendingAction.business_id == business_id, PendingAction.tier == 2, PendingAction.status == "pending",
        PendingAction.expires_at > utcnow())
    if exclude_pending_id is not None:
        q = q.where(PendingAction.id != exclude_pending_id)
    return float(session.scalar(q) or 0)


def daily_money_used(session: Session, business_id: int, *, exclude_pending_id: int | None = None) -> float:
    """Executed sandbox transfers today + still-pending Tier-2 requests (reserved against the cap)."""
    start, end = local_day_bounds_utc(local_today())
    executed = session.scalar(select(func.coalesce(func.sum(SandboxTransfer.amount), 0)).where(
        SandboxTransfer.business_id == business_id, SandboxTransfer.status == "executed",
        SandboxTransfer.executed_at >= start, SandboxTransfer.executed_at < end)) or 0
    q = select(func.coalesce(func.sum(PendingAction.amount), 0)).where(
        PendingAction.business_id == business_id, PendingAction.tier == 2, PendingAction.status == "pending",
        PendingAction.expires_at > utcnow())
    if exclude_pending_id is not None:
        q = q.where(PendingAction.id != exclude_pending_id)
    pending = session.scalar(q) or 0
    return float(executed) + float(pending)


def authorize(session: Session, user: User, tool_name: str, tier: int, *, amount: float | None = None,
              settings: Settings | None = None, exclude_pending_id: int | None = None) -> Decision:
    s = settings or get_settings()
    if tier >= 3:
        return Decision(False, False, tier, "blocked",
                        f"'{tool_name}' is a blocked action ({TIER_NAMES[3]}). The copilot never performs it.")
    max_tier = ROLE_MAX_TIER.get(user.role, -1)
    if tier > max_tier:
        return Decision(False, False, tier, "role",
                        f"Your role '{user.role}' allows up to {TIER_NAMES.get(max_tier, 'nothing')}; "
                        f"'{tool_name}' needs {TIER_NAMES[tier]}.")
    if tier == 2:
        if amount is None or amount <= 0:
            return Decision(False, False, tier, "invalid_amount", "Amount must be greater than zero.")
        if amount > s.sandbox_per_txn_limit:
            return Decision(False, False, tier, "limit_txn",
                            f"Amount {amount:,.0f} exceeds the per-transaction limit of {s.sandbox_per_txn_limit:,.0f} BDT.")
        used = daily_money_used(session, user.business_id, exclude_pending_id=exclude_pending_id)
        if used + amount > s.sandbox_daily_cap:
            return Decision(False, False, tier, "limit_daily",
                            f"Daily cap {s.sandbox_daily_cap:,.0f} BDT would be exceeded "
                            f"(already used or reserved today: {used:,.0f}).")
        acct = session.scalar(select(SandboxAccount).where(SandboxAccount.business_id == user.business_id))
        bal = float(acct.balance) if acct else 0.0
        reserved = pending_reserved(session, user.business_id, exclude_pending_id=exclude_pending_id)
        if bal - reserved < amount:
            return Decision(False, False, tier, "insufficient_funds",
                            f"Sandbox balance {bal:,.0f} BDT minus {reserved:,.0f} BDT reserved by pending requests "
                            f"is not enough for {amount:,.0f} BDT.")
        return Decision(True, True, tier, "ok", "Allowed after explicit confirmation by the owner.")
    return Decision(True, False, tier, "ok", "Allowed.")
