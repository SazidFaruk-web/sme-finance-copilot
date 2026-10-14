"""The single tool-execution pipeline.

    validate args -> authorize (tier / role / limits) -> [tier 2: queue for human confirmation]
    -> run handler -> validate result -> audit

The LLM never executes anything directly; it can only *propose* a tool call that goes through
this function, and ``confirm_pending`` (a separate authenticated endpoint) is the only way a
Tier-2 action is carried out.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ValidationError

from sme_copilot.config import get_settings
from sme_copilot.models import PendingAction, utcnow
from sme_copilot.security import audit
from sme_copilot.security.injection import neutralize
from sme_copilot.security.permissions import authorize

from .toolkit import REGISTRY, ToolContext, ToolDef, load_all_tools


@dataclass
class ToolOutcome:
    tool: str
    status: str  # ok | invalid_args | denied | blocked | pending_confirmation | error | unknown_tool
    tier: int | None
    args: dict[str, Any]
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    pending_action_id: int | None = None
    duration_ms: float = 0.0

    def for_model(self) -> str:
        """Compact JSON for the LLM: no row-id lists, untrusted strings neutralised."""
        payload: dict[str, Any] = {"status": self.status}
        if self.message:
            payload["message"] = self.message
        if self.pending_action_id:
            payload["pending_action_id"] = self.pending_action_id
        if self.data:
            payload["result"] = _neutralize_strings(_strip_row_ids(self.data))
        return compact_json(payload)

    def as_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "status": self.status, "tier": self.tier, "args": self.args, "data": self.data,
                "message": self.message, "pending_action_id": self.pending_action_id,
                "duration_ms": round(self.duration_ms, 1)}


MODEL_VIEW_BUDGET = 12000
# Bulky fields that the UI needs but a model rarely does; dropped first when over budget.
_BULKY = ("documents", "checks", "first_months", "series", "baseline_series", "scenario_series", "monthly",
          "items", "scheduled_items", "recurring", "upcoming", "components")


def _cap_lists(obj: Any, n: int) -> Any:
    if isinstance(obj, dict):
        return {k: _cap_lists(v, n) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_cap_lists(v, n) for v in obj[:n]]
    return obj


def compact_json(payload: dict[str, Any], budget: int = MODEL_VIEW_BUDGET) -> str:
    """Serialise a tool result for the model, shrinking it to fit the budget while ALWAYS staying valid
    JSON (a truncated JSON string confuses models and parsers alike)."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= budget:
        return text
    res = dict(payload.get("result") or {})
    for k in _BULKY:
        res.pop(k, None)
    if isinstance(res.get("trace"), dict):
        res["trace"] = {k: res["trace"].get(k) for k in ("formula", "period", "row_count")}
    for k in ("recommendations", "rejected"):
        if isinstance(res.get(k), list):
            res[k] = [{kk: vv for kk, vv in m.items() if kk not in _BULKY} for m in res[k]]
    for k, v in list(res.items()):
        if isinstance(v, list):
            res[f"{k}_total"] = len(v)  # keep true counts even when lists are capped below
    slim = {**payload, "result": res, "note": "large result abridged for the model; full detail is shown in the app"}
    for n in (12, 6, 3):
        text = json.dumps(_cap_lists(slim, n), ensure_ascii=False, default=str)
        if len(text) <= budget:
            return text
    return json.dumps({k: v for k, v in payload.items() if k != "result"} |
                      {"note": "result too large; key figures only",
                       "result_preview": {k: (v[:300] if isinstance(v, str) else v) for k, v in res.items()
                                          if isinstance(v, (int, float, str, bool))}},
                      ensure_ascii=False, default=str)


def _strip_row_ids(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_row_ids(v) for k, v in obj.items() if k not in ("row_ids",)}
    if isinstance(obj, list):
        return [_strip_row_ids(v) for v in obj[:40]]
    return obj


def _neutralize_strings(obj: Any) -> Any:
    if isinstance(obj, str):
        return neutralize(obj)
    if isinstance(obj, dict):
        return {k: _neutralize_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_neutralize_strings(v) for v in obj]
    return obj


def _dump(result: Any) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return json.loads(json.dumps(result, default=str))
    return {"value": result}


def _audit(ctx: ToolContext, tool: ToolDef | None, name: str, outcome: ToolOutcome, *, event_type: str,
           confirmation: str) -> None:
    result_summary: dict[str, Any] = {"status": outcome.status, "message": outcome.message[:300]}
    if outcome.status == "ok" and tool and tool.tier >= 1:
        result_summary["data"] = outcome.data  # actions: keep the full (masked, truncated) result
    elif outcome.status == "ok":
        trace = outcome.data.get("trace") if isinstance(outcome.data, dict) else None
        if trace:
            result_summary["rows_used"] = trace.get("row_count")
    audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                 event_type=event_type, action=name, tier=tool.tier if tool else None, inputs=outcome.args,
                 result=result_summary, confirmation_status=confirmation, request_id=ctx.request_id, commit=False)


def execute(ctx: ToolContext, name: str, raw_args: dict[str, Any] | None) -> ToolOutcome:
    load_all_tools()
    start = time.perf_counter()
    raw_args = dict(raw_args or {})
    tool = REGISTRY.get(name)
    if tool is None:
        out = ToolOutcome(name, "unknown_tool", None, raw_args, message=f"No tool named '{name}'.")
        _audit(ctx, None, name, out, event_type="tool_call", confirmation="not_required")
        ctx.session.commit()
        return out
    try:
        args = tool.args_model.model_validate(raw_args)
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())[:500]
        out = ToolOutcome(name, "invalid_args", tool.tier, raw_args, message=f"Invalid arguments: {msg}")
        _audit(ctx, tool, name, out, event_type="tool_call", confirmation="not_required")
        ctx.session.commit()
        return out
    if tool.prepare is not None:
        try:
            args = tool.prepare(ctx, args)
        except (ValueError, LookupError) as e:
            out = ToolOutcome(name, "invalid_args", tool.tier, raw_args, message=str(e)[:400])
            _audit(ctx, tool, name, out, event_type="tool_call", confirmation="not_required")
            ctx.session.commit()
            return out
    args_dict = args.model_dump(mode="json")
    amount = float(getattr(args, tool.amount_field)) if tool.amount_field else None
    decision = authorize(ctx.session, ctx.user, name, tool.tier, amount=amount)
    if decision.allowed and tool.tier >= 2 and ctx.suspicious_input:
        from sme_copilot.security.permissions import Decision
        decision = Decision(False, False, tool.tier, "suspicious_input",
                            "This message contains instruction-override patterns, so money actions are disabled for "
                            "it. If you really want to make a payment, ask again in plain words.")
    if not decision.allowed:
        status = "blocked" if decision.code == "blocked" else "denied"
        out = ToolOutcome(name, status, tool.tier, args_dict, message=decision.reason,
                          data={"decision": decision.as_dict()})
        _audit(ctx, tool, name, out, event_type="permission_denied",
               confirmation="blocked" if status == "blocked" else "rejected")
        ctx.session.commit()
        return out

    if decision.requires_confirmation:
        summary = tool.summarize(args) if tool.summarize else f"{name}({args_dict})"
        pa = PendingAction(business_id=ctx.business.id, user_id=ctx.user.id, tool=name, args=args_dict,
                           tier=tool.tier, summary=summary, amount=amount or 0,
                           recipient=str(getattr(args, tool.recipient_field, "") if tool.recipient_field else "")[:200],
                           origin=ctx.origin, request_id=ctx.request_id,
                           expires_at=utcnow() + timedelta(minutes=get_settings().confirmation_ttl_minutes))
        ctx.session.add(pa)
        ctx.session.flush()
        out = ToolOutcome(name, "pending_confirmation", tool.tier, args_dict, pending_action_id=pa.id,
                          message=f"Waiting for the owner's confirmation in the app: {summary}",
                          data={"summary": summary, "amount": amount, "recipient": pa.recipient,
                                "expires_at": pa.expires_at.isoformat()})
        _audit(ctx, tool, name, out, event_type="operation", confirmation="pending")
        ctx.session.commit()
        return out

    out = run_handler(ctx, tool, args, args_dict)
    out.duration_ms = (time.perf_counter() - start) * 1000
    return out


def run_handler(ctx: ToolContext, tool: ToolDef, args: BaseModel, args_dict: dict[str, Any], *,
                confirmation: str = "not_required") -> ToolOutcome:
    try:
        result = tool.handler(ctx, args)
        if tool.result_model is not None and not isinstance(result, tool.result_model):
            result = tool.result_model.model_validate(result)
        data = _dump(result)
        out = ToolOutcome(tool.name, "ok", tool.tier, args_dict, data=data)
    except (ValueError, LookupError, PermissionError) as e:
        ctx.session.rollback()
        out = ToolOutcome(tool.name, "error", tool.tier, args_dict, message=str(e)[:400])
    if tool.mutates:
        ctx.invalidate()
    event_type = "operation" if tool.tier >= 1 else "tool_call"
    _audit(ctx, tool, tool.name, out, event_type=event_type, confirmation=confirmation)
    ctx.session.commit()
    return out


class ConfirmationError(Exception):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def confirm_pending(ctx: ToolContext, pending_id: int, *, confirm_amount: float | None) -> ToolOutcome:
    """Human-in-the-loop confirmation of a Tier-2 action. Reachable only from the authenticated
    POST /api/actions/{id}/confirm endpoint - there is deliberately no tool for it, so the model
    cannot confirm its own request."""
    load_all_tools()
    pa = ctx.session.get(PendingAction, pending_id)
    if pa is None or pa.business_id != ctx.business.id:
        raise ConfirmationError("pending action not found", "not_found")
    if pa.status != "pending":
        raise ConfirmationError(f"action is already {pa.status}", "not_pending")
    tool = REGISTRY.get(pa.tool)
    if tool is None:
        raise ConfirmationError("tool no longer exists", "invalid")
    if pa.expires_at < utcnow():
        pa.status, pa.decided_at, pa.decided_by = "expired", utcnow(), ctx.user.username
        audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                     event_type="operation", action=pa.tool, tier=pa.tier, inputs=pa.args,
                     result={"status": "expired", "pending_action_id": pa.id}, confirmation_status="expired",
                     request_id=pa.request_id)
        raise ConfirmationError("confirmation window expired; please create the request again", "expired")
    if confirm_amount is None or abs(float(confirm_amount) - float(pa.amount)) > 0.005:
        audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                     event_type="security", action="confirm_amount_mismatch", tier=pa.tier,
                     inputs={"pending_action_id": pa.id, "typed_amount": confirm_amount},
                     result={"expected": pa.amount}, confirmation_status="rejected", request_id=pa.request_id)
        raise ConfirmationError("the amount you typed does not match the request; nothing was sent", "amount_mismatch")
    # Re-check permissions at execution time: role, limits and balance may have changed.
    decision = authorize(ctx.session, ctx.user, pa.tool, pa.tier, amount=float(pa.amount),
                         exclude_pending_id=pa.id)
    if not decision.allowed:
        pa.status, pa.decided_at, pa.decided_by = "rejected", utcnow(), ctx.user.username
        pa.result = {"reason": decision.reason}
        out = ToolOutcome(pa.tool, "denied", pa.tier, pa.args, message=decision.reason)
        _audit(ctx, tool, pa.tool, out, event_type="permission_denied", confirmation="rejected")
        ctx.session.commit()
        return out
    args = tool.args_model.model_validate(pa.args)
    ctx.origin = "confirmation"
    ctx.pending_action_id = pa.id
    out = run_handler(ctx, tool, args, pa.args, confirmation="confirmed")
    pa.status = "confirmed" if out.status == "ok" else "failed"
    pa.decided_at, pa.decided_by = utcnow(), ctx.user.username
    pa.result = {"status": out.status, "message": out.message, **({"data": out.data} if out.status == "ok" else {})}
    ctx.session.commit()
    return out


def reject_pending(ctx: ToolContext, pending_id: int) -> None:
    pa = ctx.session.get(PendingAction, pending_id)
    if pa is None or pa.business_id != ctx.business.id:
        raise ConfirmationError("pending action not found", "not_found")
    if pa.status != "pending":
        raise ConfirmationError(f"action is already {pa.status}", "not_pending")
    pa.status, pa.decided_at, pa.decided_by = "rejected", utcnow(), ctx.user.username
    audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                 event_type="operation", action=pa.tool, tier=pa.tier, inputs=pa.args,
                 result={"status": "rejected_by_user", "pending_action_id": pa.id}, confirmation_status="rejected",
                 request_id=pa.request_id)
