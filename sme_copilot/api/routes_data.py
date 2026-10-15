"""Data ingestion and browsing endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.agent.executor import execute
from sme_copilot.db import get_db
from sme_copilot.models import ImportBatch, Invoice, Transaction, User
from sme_copilot.security import audit
from sme_copilot.security.pii import mask_account
from sme_copilot.tools.categorize import all_category_names
from sme_copilot.tools.ingestion import DOC_TYPES, import_file, refresh_anomalies, text_to_bytes
from sme_copilot.tools import stock
from sme_copilot.tools.nl_entry import parse_entry
from sme_copilot.tools.record_resolver import fast_path, resolve_record

from .deps import as_of_today, current_user, require_tier, tool_context
from .schemas import EntryIn, PasteIn, TxnPatch

router = APIRouter(prefix="/api/data")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = (".csv", ".tsv", ".txt", ".xlsx", ".xls")


def _import(db: Session, user: User, content: bytes, filename: str, doc_type: str) -> dict[str, Any]:
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {DOC_TYPES}")
    try:
        rep = import_file(db, user.business_id, content, filename, doc_type=doc_type, actor=user.username)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from e
    d = rep.to_dict()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="import_file", tier=1, inputs={"filename": filename, "doc_type": doc_type},
                 result={k: (len(v) if isinstance(v, list) else v) for k, v in d.items()
                         if k in ("doc_type", "rows_total", "imported", "duplicates", "anomalies", "injection_flags",
                                  "errors", "already_imported", "batch_id")})
    return d


@router.post("/upload")
async def upload(file: UploadFile = File(...), doc_type: str = Form("auto"), user: User = Depends(require_tier(1)),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    name = (file.filename or "upload.csv").replace("\\", "/").split("/")[-1][:200]
    if not name.lower().endswith(ALLOWED_EXT):
        raise HTTPException(415, f"allowed file types: {', '.join(ALLOWED_EXT)}")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (max 5 MB)")
    return _import(db, user, content, name, doc_type)


@router.post("/paste")
def paste(body: PasteIn, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)) -> dict[str, Any]:
    return _import(db, user, text_to_bytes(body.text), "pasted.csv", body.doc_type)


@router.post("/entry/preview")
def entry_preview(body: EntryIn, user: User = Depends(current_user)) -> dict[str, Any]:
    out = parse_entry(body.text, as_of_today()).to_dict()
    ex = fast_path(body.text)  # no LLM call while typing
    if ex:
        r = resolve_record(ex)
        out.update(amount=r["amount"], direction=r["direction"], category=r["category"], quantity=r["quantity"],
                   item=r["item"], needs_confirm=r["needs_confirm"], preview=r["preview"], missing=[])
    return out


@router.post("/entry")
def entry(body: EntryIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    out = execute(tool_context(db, user), "add_transaction", {"text": body.text, "confirmed": body.confirmed})
    if out.status in ("denied", "blocked"):
        raise HTTPException(403, out.message)
    return out.as_dict()


def _txn_dict(t: Transaction) -> dict[str, Any]:
    return {"id": t.id, "date": t.txn_date.isoformat(), "amount": float(t.amount), "direction": t.direction,
            "category": t.category, "counterparty": t.counterparty, "description": t.description,
            "channel": t.channel, "account": mask_account(t.account_ref), "reference": t.reference,
            "source": t.source, "batch_id": t.batch_id, "source_row": t.source_row, "flags": t.flags or [],
            "is_duplicate": t.is_duplicate, "duplicate_of": t.duplicate_of, "is_anomaly": t.is_anomaly,
            "anomaly_reason": t.anomaly_reason, "categorized_by": t.categorized_by,
            "category_confidence": t.category_confidence}


@router.get("/transactions")
def transactions(limit: int = 100, offset: int = 0, category: str = "", flagged: bool = False,
                 ids: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    q = select(Transaction).where(Transaction.business_id == user.business_id)
    if ids:  # explainability: fetch the exact rows a trace refers to
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()][:200]
        q = q.where(Transaction.id.in_(id_list))
    if category:
        q = q.where(Transaction.category == category)
    if flagged:
        q = q.where((Transaction.is_duplicate.is_(True)) | (Transaction.is_anomaly.is_(True)))
    rows = db.scalars(q.order_by(Transaction.txn_date.desc(), Transaction.id.desc())
                      .offset(max(0, offset)).limit(min(limit, 500))).all()
    return {"rows": [_txn_dict(t) for t in rows], "categories": all_category_names()}


@router.delete("/transactions/{txn_id}")
def undo_entry(txn_id: int, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Undo a just-added quick entry (typed records only, not imported rows)."""
    t = db.get(Transaction, txn_id)
    if t is None or t.business_id != user.business_id:
        raise HTTPException(404, "transaction not found")
    if t.source not in ("nl", "manual"):
        raise HTTPException(409, "only quick entries can be undone")
    snap = _txn_dict(t)
    stock.reverse_for_transaction(db, t.id)
    db.delete(t)
    refresh_anomalies(db, user.business_id)
    db.commit()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="undo_entry", tier=1, inputs={"id": txn_id}, result={"deleted": snap})
    return {"deleted": txn_id}


@router.patch("/transactions/{txn_id}")
def patch_transaction(txn_id: int, body: TxnPatch, user: User = Depends(require_tier(1)),
                      db: Session = Depends(get_db)) -> dict[str, Any]:
    t = db.get(Transaction, txn_id)
    if t is None or t.business_id != user.business_id:
        raise HTTPException(404, "transaction not found")
    before = {"category": t.category, "is_duplicate": t.is_duplicate}
    if body.category is not None:
        if body.category not in all_category_names():
            raise HTTPException(422, "unknown category")
        t.category, t.categorized_by, t.category_confidence = body.category, "user", 1.0
        stock.relink_after_edit(db, t)
    if body.is_duplicate is not None:
        t.is_duplicate = body.is_duplicate
        t.flags = [f for f in (t.flags or []) if f != "duplicate"] + (["duplicate"] if body.is_duplicate else [])
    db.flush()
    refresh_anomalies(db, user.business_id)
    db.commit()
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="operation",
                 action="edit_transaction", tier=1, inputs={"id": txn_id, "before": before,
                                                           "after": body.model_dump(exclude_none=True)})
    return _txn_dict(t)


@router.get("/invoices")
def invoices(kind: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(Invoice).where(Invoice.business_id == user.business_id)
    if kind:
        q = q.where(Invoice.kind == kind)
    return [{"id": i.id, "kind": i.kind, "invoice_no": i.invoice_no, "counterparty": i.counterparty,
             "phone": mask_account(i.counterparty_phone), "amount": float(i.amount),
             "amount_paid": float(i.amount_paid or 0), "issue_date": i.issue_date.isoformat(),
             "due_date": i.due_date.isoformat(), "paid_date": i.paid_date.isoformat() if i.paid_date else None,
             "status": i.status, "source": i.source, "source_row": i.source_row}
            for i in db.scalars(q.order_by(Invoice.due_date)).all()]


@router.get("/imports")
def imports(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(ImportBatch).where(ImportBatch.business_id == user.business_id)
                      .order_by(ImportBatch.id.desc())).all()
    return [{"id": b.id, "filename": b.filename, "doc_type": b.doc_type, "rows_total": b.rows_total,
             "imported": b.imported, "duplicates": b.duplicates, "anomalies": b.anomalies,
             "injection_flags": b.injection_flags, "created_by": b.created_by, "created_at": b.created_at.isoformat()}
            for b in rows]
