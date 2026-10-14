"""Action layer API: human-in-the-loop confirmations, outbox, drafts, reports, sandbox, operation log, privacy."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sme_copilot.agent.executor import ConfirmationError, confirm_pending, execute, reject_pending
from sme_copilot.config import get_settings
from sme_copilot.db import get_db
from sme_copilot.models import (
    Alert,
    AuditEvent,
    AuthSession,
    Business,
    ChatMessage,
    Conversation,
    Draft,
    ImportBatch,
    Invoice,
    Obligation,
    PendingAction,
    Reminder,
    Report,
    SandboxAccount,
    SandboxTransfer,
    Transaction,
    User,
    utcnow,
)
from sme_copilot.security import audit
from sme_copilot.security.auth import verify_password
from sme_copilot.security.permissions import daily_money_used
from sme_copilot.security.pii import mask_account
from sme_copilot.telemetry.interactions import purge_business

from .deps import current_user, require_owner, require_tier, tool_context
from .schemas import ConfirmIn, DeleteDataIn

router = APIRouter(prefix="/api")

OPLOG_TYPES = ("operation", "permission_denied", "security")


# ----------------------------------------------------------------------------- confirmations
def _pending_dict(p: PendingAction) -> dict[str, Any]:
    return {"id": p.id, "tool": p.tool, "tier": p.tier, "summary": p.summary, "amount": float(p.amount),
            "recipient": p.recipient, "status": p.status, "origin": p.origin, "created_at": p.created_at.isoformat(),
            "expires_at": p.expires_at.isoformat(), "decided_at": p.decided_at.isoformat() if p.decided_at else None,
            "decided_by": p.decided_by, "result": p.result or {}}


@router.get("/actions/pending")
def pending(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(PendingAction).where(PendingAction.business_id == user.business_id)
                      .order_by(PendingAction.id.desc()).limit(50)).all()
    now = utcnow()
    for p in rows:
        if p.status == "pending" and p.expires_at < now:
            p.status = "expired"
    db.commit()
    return [_pending_dict(p) for p in rows]


@router.post("/actions/{pending_id}/confirm")
def confirm(pending_id: int, body: ConfirmIn, user: User = Depends(require_tier(2)),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    ctx = tool_context(db, user, origin="confirmation")
    try:
        out = confirm_pending(ctx, pending_id, confirm_amount=body.confirm_amount)
    except ConfirmationError as e:
        db.commit()
        code = {"not_found": 404, "expired": 410, "amount_mismatch": 409, "not_pending": 409}.get(e.code, 400)
        raise HTTPException(code, str(e)) from e
    if out.status == "denied":
        raise HTTPException(403, out.message)
    return out.as_dict()


@router.post("/actions/{pending_id}/reject")
def reject(pending_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    ctx = tool_context(db, user)
    try:
        reject_pending(ctx, pending_id)
    except ConfirmationError as e:
        raise HTTPException(404 if e.code == "not_found" else 409, str(e)) from e
    return {"status": "rejected"}


# ----------------------------------------------------------------------------- outbox / drafts / reports
@router.get("/reminders")
def reminders(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Reminder).where(Reminder.business_id == user.business_id).order_by(Reminder.id.desc())).all()
    return [{"id": r.id, "invoice_id": r.invoice_id, "counterparty": r.counterparty, "amount": float(r.amount),
             "remind_on": r.remind_on.isoformat(), "channel": r.channel, "message": r.message, "status": r.status,
             "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/drafts")
def drafts(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Draft).where(Draft.business_id == user.business_id).order_by(Draft.id.desc())).all()
    return [{"id": d.id, "kind": d.kind, "invoice_id": d.invoice_id, "recipient": d.recipient, "language": d.language,
             "tone": d.tone, "subject": d.subject, "body": d.body, "status": d.status,
             "created_at": d.created_at.isoformat()} for d in rows]


class DraftPatch(BaseModel):
    status: Literal["draft", "approved", "discarded"] | None = None
    body: str | None = Field(None, max_length=5000)


@router.patch("/drafts/{draft_id}")
def patch_draft(draft_id: int, body: DraftPatch, user: User = Depends(require_tier(1)),
                db: Session = Depends(get_db)) -> dict[str, Any]:
    d = db.get(Draft, draft_id)
    if d is None or d.business_id != user.business_id:
        raise HTTPException(404, "draft not found")
    if body.body is not None:
        d.body = body.body
    if body.status:
        d.status = body.status
    db.commit()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="update_draft", tier=1, inputs={"draft_id": draft_id, **body.model_dump(exclude_none=True)})
    return {"id": d.id, "status": d.status}


@router.get("/reports")
def reports(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Report).where(Report.business_id == user.business_id).order_by(Report.id.desc())).all()
    return [{"id": r.id, "kind": r.kind, "filename": r.filename, "sha256": r.sha256, "params": r.params,
             "created_at": r.created_at.isoformat(), "download_url": f"/api/reports/{r.id}/download"} for r in rows]


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    r = db.get(Report, report_id)
    if r is None or r.business_id != user.business_id or not r.filename:
        raise HTTPException(404, "report not found")
    path = (get_settings().reports_dir / r.filename).resolve()
    if get_settings().reports_dir.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "report file missing")
    return FileResponse(path, media_type="application/pdf", filename=r.filename)


# ----------------------------------------------------------------------------- sandbox
@router.get("/sandbox")
def sandbox(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    acct = db.scalar(select(SandboxAccount).where(SandboxAccount.business_id == user.business_id))
    s = get_settings()
    transfers = db.scalars(select(SandboxTransfer).where(SandboxTransfer.business_id == user.business_id)
                           .order_by(SandboxTransfer.id.desc()).limit(30)).all()
    return {"account": {"name": acct.name, "account_no": mask_account(acct.account_no), "balance": float(acct.balance),
                        "currency": acct.currency} if acct else None,
            "limits": {"per_transaction": s.sandbox_per_txn_limit, "daily_cap": s.sandbox_daily_cap,
                       "used_or_reserved_today": daily_money_used(db, user.business_id),
                       "confirmation_ttl_minutes": s.confirmation_ttl_minutes},
            "transfers": [{"id": t.id, "kind": t.kind, "recipient": t.recipient_name,
                           "account": mask_account(t.recipient_account), "amount": float(t.amount), "purpose": t.purpose,
                           "status": t.status, "balance_after": float(t.balance_after or 0),
                           "executed_at": t.executed_at.isoformat() if t.executed_at else None,
                           "pending_action_id": t.pending_action_id} for t in transfers]}


# ----------------------------------------------------------------------------- operation log
def _oplog_rows(db: Session, business_id: int, limit: int) -> list[AuditEvent]:
    return list(db.scalars(select(AuditEvent).where(AuditEvent.business_id == business_id,
                                                    AuditEvent.event_type.in_(OPLOG_TYPES))
                           .order_by(AuditEvent.id.desc()).limit(limit)))


@router.get("/oplog")
def oplog(limit: int = 200, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [audit.to_dict(e) for e in _oplog_rows(db, user.business_id, min(limit, 2000))]


@router.get("/oplog/export")
def oplog_export(fmt: Literal["csv", "jsonl"] = "csv", user: User = Depends(require_tier(1)),
                 db: Session = Depends(get_db)) -> Response:
    rows = list(reversed(_oplog_rows(db, user.business_id, 10_000)))
    if fmt == "jsonl":
        text = "\n".join(json.dumps(audit.to_dict(e), ensure_ascii=False, default=str) for e in rows) + "\n"
        return PlainTextResponse(text, media_type="application/x-ndjson",
                                 headers={"Content-Disposition": "attachment; filename=operation_log.jsonl"})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "timestamp_utc", "actor", "actor_role", "event_type", "action", "tier", "inputs", "result",
                "confirmation_status", "request_id", "prev_hash", "hash"])
    for e in rows:
        w.writerow([e.id, e.ts.isoformat(), e.actor, e.actor_role, e.event_type, e.action, e.tier,
                    json.dumps(e.inputs, ensure_ascii=False), json.dumps(e.result, ensure_ascii=False, default=str),
                    e.confirmation_status, e.request_id, e.prev_hash, e.hash])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=operation_log.csv"})


# ----------------------------------------------------------------------------- obligations / compliance
@router.get("/obligations")
def obligations(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Obligation).where(Obligation.business_id == user.business_id)).all()
    return [{"id": o.id, "name": o.name, "category": o.category, "amount": float(o.amount), "frequency": o.frequency,
             "day_of_month": o.day_of_month, "next_due": o.next_due.isoformat(), "active": o.active} for o in rows]


@router.get("/compliance")
def compliance(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    out = execute(tool_context(db, user), "compliance_info", {"topic": "all"})
    return out.data


# ----------------------------------------------------------------------------- privacy
BUSINESS_TABLES = [ChatMessage, Conversation, PendingAction, SandboxTransfer, SandboxAccount, Reminder, Draft, Report,
                   Alert, Obligation, Transaction, Invoice, ImportBatch]


@router.post("/privacy/delete")
def delete_my_data(body: DeleteDataIn, user: User = Depends(require_owner), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Right to erasure: deletes all business data, generated files and the interaction dataset lines for this
    business, and deactivates all its user accounts. The hash-chained audit log is kept (it stores only masked,
    minimal data) so the deletion itself remains provable."""
    if not verify_password(body.password, user.password_hash):
        audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="security",
                     action="delete_data_bad_password")
        raise HTTPException(403, "password incorrect")
    bid = user.business_id
    counts: dict[str, int] = {}
    for r in db.scalars(select(Report).where(Report.business_id == bid)):
        f = get_settings().reports_dir / r.filename
        if r.filename and f.exists():
            f.unlink()
    conv_ids = [c.id for c in db.scalars(select(Conversation).where(Conversation.business_id == bid))]
    if conv_ids:
        counts["chat_messages"] = db.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(conv_ids))).rowcount
    for model in BUSINESS_TABLES[1:]:
        counts[model.__tablename__] = db.execute(delete(model).where(model.business_id == bid)).rowcount
    b = db.get(Business, bid)
    b.name, b.owner_name, b.tin, b.trade_license_no, b.prefs = "deleted business", "", None, None, {}
    users = list(db.scalars(select(User).where(User.business_id == bid)))
    for u in users:
        u.is_active = False
        db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))
    db.commit()
    purged = purge_business(bid)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=bid, event_type="data",
                 action="delete_business_data", inputs={"confirm": body.confirm},
                 result={"rows_deleted": counts, "interaction_lines_purged": purged, "users_deactivated": len(users)})
    return {"status": "deleted", "rows_deleted": counts, "interaction_lines_purged": purged,
            "note": "Audit log retained with masked data to prove what happened, including this deletion."}


@router.get("/privacy/export")
def export_my_data(user: User = Depends(require_owner), db: Session = Depends(get_db)) -> Response:
    bid = user.business_id
    data = {
        "business": {k: getattr(db.get(Business, bid), k) for k in ("name", "sector", "district", "established_on")},
        "transactions": [{"date": t.txn_date, "amount": float(t.amount), "direction": t.direction, "category": t.category,
                          "counterparty": t.counterparty, "description": t.description, "channel": t.channel,
                          "account": t.account_ref, "source": t.source}
                         for t in db.scalars(select(Transaction).where(Transaction.business_id == bid))],
        "invoices": [{"kind": i.kind, "invoice_no": i.invoice_no, "counterparty": i.counterparty,
                      "phone": i.counterparty_phone, "amount": float(i.amount), "due_date": i.due_date, "status": i.status}
                     for i in db.scalars(select(Invoice).where(Invoice.business_id == bid))],
    }
    audit.record(db, actor=user.username, actor_role=user.role, business_id=bid, event_type="data",
                 action="export_business_data", result={"transactions": len(data["transactions"]),
                                                        "invoices": len(data["invoices"])})
    return Response(json.dumps(data, ensure_ascii=False, default=str, indent=1), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=my_business_data.json"})
