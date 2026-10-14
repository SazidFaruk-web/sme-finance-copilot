"""Action-layer tools: Tier 1 (drafts, reminders, reports), Tier 2 (sandbox money), Tier 3 (blocked)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .toolkit import ToolContext, tool


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
