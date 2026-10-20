"""Business-scoped guided cases. Every effect requires a fresh, single-use preview."""
from __future__ import annotations

import base64
import secrets
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sme_copilot.config import get_settings
from sme_copilot.db import get_db
from sme_copilot.models import Alert, Business, User, utcnow
from sme_copilot.security import audit
from sme_copilot.pilot.definitions import KINDS, questions
from sme_copilot.pilot.knowledge import sources
from sme_copilot.pilot.models import CaseDocument, GuidedCase, NotificationDelivery, NotificationPreference, ReminderJob
from sme_copilot.pilot.service import build_preview, commit_action, fail, snapshot, validate, view
from .deps import as_of_today, current_user, require_owner, require_tier

router = APIRouter(prefix="/api/pilot", tags=["guided tasks"])


def sms_ready():
    s = get_settings()
    return bool(s.pilot_sms_enabled and s.pilot_sms_api_token and s.pilot_sms_sid)


def own(db, user, case_id):
    case = db.get(GuidedCase, case_id)
    if not case or case.business_id != user.business_id:
        fail("not_found", 404)
    return case


def event(db, user, case, action):
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id,
                 event_type="operation", action=action, tier=1, inputs={"case_id": case.id}, commit=False)


@router.get("/catalog")
def catalog(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"workflows": [{"id": k, "title": v} for k, v in KINDS.items()],
            "sources": sources(db, as_of_today()), "sms_available": sms_ready(),
            "today": as_of_today().isoformat(), "help_contact": get_settings().pilot_help_contact}


class Suggest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: Literal["en", "bn"] = "en"


@router.post("/suggest")
def suggest(body: Suggest, user: User = Depends(current_user)):
    from sme_copilot.pilot.question_model import choose_goal
    return {"kinds": choose_goal(body.text)}


@router.get("/documents")
def document_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(CaseDocument).where(CaseDocument.business_id == user.business_id)
                      .order_by(CaseDocument.id.desc()).limit(200))
    return [{"id": d.id, "case_id": d.case_id, "name": d.name, "stage": d.stage} for d in rows]


class CreateCase(BaseModel):
    kind: Literal["record", "collect", "shortfall", "loan", "stock", "paperwork", "strategy"]
    language: Literal["en", "bn"] = "en"
    request_key: str = Field(min_length=8, max_length=80)
    plan_type: Literal["seasonal", "bulk", "equipment"] | None = None


@router.get("/strategy")
def strategy_ideas(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from sme_copilot.pilot.strategy import ideas
    return ideas(db.get(Business, user.business_id))


@router.post("/cases")
def create(body: CreateCase, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)):
    old = db.scalar(select(GuidedCase).where(GuidedCase.business_id == user.business_id, GuidedCase.request_key == body.request_key))
    if old:
        if old.kind != body.kind:
            fail("conflict", 409)
        return view(db, old, as_of_today())
    if body.plan_type and body.kind != "strategy":
        fail("invalid_question")
    case = GuidedCase(business_id=user.business_id, user_id=user.id, **body.model_dump(exclude={"plan_type"}),
                      answers={"plan_type": body.plan_type} if body.plan_type else {})
    db.add(case)
    try:
        db.flush()
        event(db, user, case, "guided_start")
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("conflict", 409)
    return view(db, case, as_of_today())


@router.get("/cases")
def cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(GuidedCase).where(GuidedCase.business_id == user.business_id)
                      .order_by(GuidedCase.updated_at.desc()).limit(100))
    return [{"id": c.id, "kind": c.kind, "title": KINDS[c.kind], "status": c.status,
             "item": c.answers.get("item") if c.kind == "strategy" else None,
             "updated_at": c.updated_at.isoformat(), "result": c.result} for c in rows]


@router.get("/cases/{case_id}")
def get_case(case_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return view(db, own(db, user, case_id), as_of_today())


class Answer(BaseModel):
    version: int
    question_id: str = Field(max_length=40)
    value: Any = None
    language: Literal["en", "bn"] = "en"


@router.post("/cases/{case_id}/answer")
def answer(case_id: int, body: Answer, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)):
    case = own(db, user, case_id)
    today = as_of_today()
    snap = snapshot(db, user.business_id, today)
    qs = questions(case.kind, case.answers, snap)
    question = next((q for q in qs if q["id"] == body.question_id), None)
    if not question:
        fail("invalid_question")
    values = {**case.answers, body.question_id: validate(question, body.value, today)}
    valid_ids = {q["id"] for q in questions(case.kind, values, snap)}
    values = {k: v for k, v in values.items() if k in valid_ids}
    updated = db.execute(update(GuidedCase).where(GuidedCase.id == case.id, GuidedCase.version == body.version,
                         GuidedCase.status.in_(["active", "paused"]))
                         .values(answers=values, version=GuidedCase.version + 1, preview={}, result={}, status="active",
                                 language=body.language, updated_at=utcnow()))
    if updated.rowcount != 1:
        fail("conflict", 409)
    db.commit(); db.expire_all()
    return view(db, own(db, user, case_id), today)


class Control(BaseModel):
    version: int
    action: Literal["pause", "continue", "reopen", "complete"]


@router.post("/cases/{case_id}/control")
def control(case_id: int, body: Control, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)):
    case = own(db, user, case_id)
    # Completed records cannot be replayed; existing record correction is handled by bookkeeping.
    if case.status == "completed" and (case.kind == "record" or body.action != "complete"):
        fail("already_completed", 409)
    state = "paused" if body.action == "pause" else "completed" if body.action == "complete" else "active"
    if body.action == "complete" and case.status != "completed":
        fail("review_first", 409)
    changed = db.execute(update(GuidedCase).where(GuidedCase.id == case.id, GuidedCase.version == body.version)
                         .values(status=state, checkpoint=len(case.answers), version=GuidedCase.version + 1,
                                 preview={}, updated_at=utcnow()))
    if changed.rowcount != 1:
        fail("conflict", 409)
    if body.action == "complete":
        for job in db.scalars(select(ReminderJob).where(ReminderJob.case_id == case.id)):
            job.active = False
            db.get(Alert, job.alert_id).status = "acknowledged"
    db.commit(); db.expire_all()
    return view(db, own(db, user, case_id), as_of_today())


class PreviewIn(BaseModel):
    version: int
    action: str = Field(max_length=30)
    language: Literal["en", "bn"] = "en"
    text: str | None = Field(None, min_length=1, max_length=12000)


@router.post("/cases/{case_id}/preview")
def preview(case_id: int, body: PreviewIn, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)):
    case = own(db, user, case_id)
    case.language = body.language
    payload = build_preview(db, case, as_of_today(), body.action, body.text)
    payload["token"] = secrets.token_urlsafe(24)
    changed = db.execute(update(GuidedCase).where(GuidedCase.id == case.id, GuidedCase.version == body.version,
                          GuidedCase.status == "active").values(preview=payload, version=GuidedCase.version + 1))
    if changed.rowcount != 1:
        fail("conflict", 409)
    db.commit(); db.expire_all()
    return view(db, own(db, user, case_id), as_of_today())


class Confirm(BaseModel):
    version: int
    token: str = Field(min_length=10, max_length=100)


@router.post("/cases/{case_id}/confirm")
def confirm(case_id: int, body: Confirm, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    case = own(db, user, case_id)
    payload = case.preview
    if not payload or not secrets.compare_digest(payload.get("token", ""), body.token):
        fail("review_first", 409)
    if case.status == "completed":
        return view(db, case, as_of_today())  # idempotent retry of this exact confirmed preview
    if payload["fingerprint"] != snapshot(db, user.business_id, as_of_today())["fingerprint"]:
        fail("records_changed", 409)
    changed = db.execute(update(GuidedCase).where(GuidedCase.id == case.id, GuidedCase.version == body.version,
                          GuidedCase.status == "active").values(status="confirming", version=GuidedCase.version + 1))
    if changed.rowcount != 1:
        fail("conflict", 409)
    commit_action(db, case, payload, as_of_today())
    event(db, user, case, "guided_confirm")
    db.commit(); db.expire_all()
    return view(db, own(db, user, case_id), as_of_today())


@router.post("/cases/{case_id}/attachments")
async def attachment(case_id: int, file: UploadFile = File(...), user: User = Depends(require_tier(1)), db: Session = Depends(get_db)):
    case = own(db, user, case_id)
    raw = await file.read(5_000_001)
    await file.close()
    if len(raw) > 5_000_000 or len(raw) == 0:
        fail("file_size")
    mime = "application/pdf" if raw.startswith(b"%PDF-") else "image/png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if raw.startswith(b"\xff\xd8\xff") else None
    if not mime:
        fail("file_type")
    name = (file.filename or "document").replace("\\", "/").split("/")[-1][:140]
    d = CaseDocument(business_id=user.business_id, case_id=case.id, name=name, mime=mime,
                     content=base64.b64encode(raw).decode(), attachment=True)
    if case.status != "completed":
        case.preview = {}
    else:
        case.result = {**case.result, "evidence_changed": True,
                       "human_review": "pending" if case.kind in ("loan", "paperwork", "strategy") else "not_required"}
    case.version += 1
    case.updated_at = utcnow()
    db.add(d); db.flush(); event(db, user, case, "guided_attachment"); db.commit()
    return {"id": d.id, "name": d.name}


def own_document(db, user, document_id):
    d = db.get(CaseDocument, document_id)
    if not d or d.business_id != user.business_id:
        fail("not_found", 404)
    return d


@router.get("/documents/{document_id}/download")
def document(document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = own_document(db, user, document_id)
    data = base64.b64decode(d.content) if d.attachment else d.content.encode("utf-8")
    ext = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}.get(d.mime, "txt")
    return Response(data, media_type=d.mime, headers={"Content-Disposition": f'attachment; filename="document-{d.id}.{ext}"'})


class DocumentChange(BaseModel):
    body: str | None = Field(None, min_length=1, max_length=12000)
    stage: Literal["prepared", "submitted", "accepted"] | None = None
    reference: str = Field("", max_length=180)


@router.patch("/documents/{document_id}")
def change_document(document_id: int, body: DocumentChange, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    d = own_document(db, user, document_id)
    if body.body is not None:
        if d.attachment or d.stage != "prepared":
            fail("document_locked")
        d.content = body.body
    if body.stage:
        allowed = {"prepared": {"prepared", "submitted"}, "submitted": {"submitted", "accepted"}, "accepted": {"accepted"}}
        if body.stage not in allowed[d.stage] or body.stage != "prepared" and not body.reference.strip():
            fail("submission_reference")
        d.stage, d.reference = body.stage, body.reference.strip()
        if d.stage == "accepted":
            for job in db.scalars(select(ReminderJob).where(ReminderJob.case_id == d.case_id)):
                job.active = False
                db.get(Alert, job.alert_id).status = "acknowledged"
    event(db, user, own(db, user, d.case_id), "guided_document_update")
    db.commit()
    return {"id": d.id, "stage": d.stage}


class ReminderChange(BaseModel):
    due_date: date | None = None
    complete: bool = False


@router.patch("/reminders/{alert_id}")
def change_reminder(alert_id: int, body: ReminderChange, user: User = Depends(require_tier(1)), db: Session = Depends(get_db)):
    job = db.scalar(select(ReminderJob).where(ReminderJob.alert_id == alert_id, ReminderJob.business_id == user.business_id))
    if not job:
        fail("not_found", 404)
    alert = db.get(Alert, alert_id)
    if body.complete:
        job.active, alert.status = False, "acknowledged"
    elif body.due_date:
        if body.due_date < as_of_today():
            fail("invalid_date")
        job.active, job.due_date, alert.due_date, alert.status = True, body.due_date, body.due_date, "scheduled"
    db.commit()
    return {"id": alert.id, "due_date": alert.due_date, "status": alert.status}


class Preferences(BaseModel):
    phone: str = Field("", max_length=20)
    consent: bool = False
    send_hour: int = Field(18, ge=7, le=21)
    language: Literal["en", "bn"] = "en"


@router.get("/notifications")
def notifications(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    p = db.get(NotificationPreference, user.id)
    rows = db.scalars(select(NotificationDelivery).where(NotificationDelivery.user_id == user.id)
                      .order_by(NotificationDelivery.id.desc()).limit(10))
    return {"consent": p.consent if p else False, "phone": p.phone if p else "", "verified": p.verified if p else False,
            "send_hour": p.send_hour if p else 18, "configured": sms_ready(),
            "deliveries": [{"id": d.id, "date": d.send_date, "status": d.status} for d in rows]}


@router.put("/notifications")
def notification_preferences(body: Preferences, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    import re
    phone = body.phone.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")).replace(" ", "")
    if phone.startswith("01"):
        phone = "+88" + phone
    if body.consent and not re.fullmatch(r"\+8801[3-9]\d{8}", phone):
        fail("invalid_phone")
    p = db.get(NotificationPreference, user.id) or NotificationPreference(user_id=user.id, business_id=user.business_id)
    if phone != p.phone:
        p.verified = False  # only an operator can record out-of-band ownership verification
    p.phone, p.consent, p.send_hour, p.language = phone, body.consent, body.send_hour, body.language
    p.consent_at = utcnow() if body.consent else None
    db.add(p); db.commit()
    return notifications(user, db)


class Outcome(BaseModel):
    units_sold: int = Field(ge=0, le=100000)
    money_received: float = Field(ge=0, le=1e8, allow_inf_nan=False)
    note: str = Field("", max_length=1000)


@router.post("/cases/{case_id}/outcome")
def outcome(case_id: int, body: Outcome, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    case = own(db, user, case_id)
    if case.kind != "stock" or case.status != "completed" or not case.result.get("test_quantity"):
        fail("invalid_action")
    if body.units_sold > case.result["test_quantity"]:
        fail("invalid_number")
    case.result = {**case.result, "outcome": {**body.model_dump(), "date": as_of_today().isoformat()}}
    event(db, user, case, "guided_outcome")
    db.commit()
    return view(db, case, as_of_today())
