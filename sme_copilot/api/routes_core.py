"""Auth, chat (incl. SSE streaming), tools, models, feedback, audit."""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.agent.executor import execute
from sme_copilot.agent.orchestrator import Agent, AgentResult
from sme_copilot.agent.toolkit import REGISTRY, load_all_tools
from sme_copilot.db import SessionLocal, get_db
from sme_copilot.llm_providers import Message, get_registry
from sme_copilot.models import AuditEvent, ChatMessage, Conversation, User
from sme_copilot.security import audit
from sme_copilot.security.auth import AuthError, authenticate, create_session, revoke_token
from sme_copilot.security.permissions import TIER_NAMES
from sme_copilot.telemetry.interactions import log_feedback, log_interaction

from .deps import bearer_token, current_user, require_tier, tool_context
from .schemas import ChatIn, FeedbackIn, LoginIn, ToolCallIn

router = APIRouter(prefix="/api")


# ----------------------------------------------------------------------------- auth
@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    ip = request.client.host if request.client else ""
    try:
        user = authenticate(db, body.username, body.password)
    except AuthError as e:
        audit.record(db, actor=body.username[:80], event_type="auth", action="login_failed",
                     inputs={"ip": ip}, result={"reason": str(e)})
        raise HTTPException(401, str(e)) from e
    token = create_session(db, user)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="auth",
                 action="login", inputs={"ip": ip})
    return {"token": token, "user": _user_dict(user)}


@router.post("/auth/logout")
def logout(token: str = Depends(bearer_token), user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> dict[str, str]:
    revoke_token(db, token)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="auth",
                 action="logout")
    return {"status": "logged_out"}


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    from sme_copilot.models import Business

    from .deps import as_of_today
    b = db.get(Business, user.business_id)
    return {**_user_dict(user), "business_name": b.name if b else "", "as_of": as_of_today().isoformat()}


def _user_dict(u: User) -> dict[str, Any]:
    from sme_copilot.security.permissions import ROLE_MAX_TIER
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "business_id": u.business_id, "max_tier": ROLE_MAX_TIER.get(u.role, 0)}


# ----------------------------------------------------------------------------- models
@router.get("/models")
def models(user: User = Depends(current_user)) -> dict[str, Any]:
    reg = get_registry()
    return {"default": reg.default_profile, "routing_enabled": bool(reg.routing.get("enabled")),
            "local_only_mode": reg.settings.local_only_mode, "mask_pii": reg.settings.mask_pii,
            "profiles": [p.__dict__ for p in reg.list_profiles()]}


# ----------------------------------------------------------------------------- chat
def _history(db: Session, conv_id: int | None) -> list[Message]:
    if not conv_id:
        return []
    rows = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
                      .order_by(ChatMessage.id.desc()).limit(8)).all()
    return [Message(r.role, r.content) for r in reversed(rows) if r.role in ("user", "assistant")]


def _conversation(db: Session, user: User, conv_id: int | None) -> Conversation:
    if conv_id:
        conv = db.get(Conversation, conv_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(404, "conversation not found")
        return conv
    conv = Conversation(business_id=user.business_id, user_id=user.id)
    db.add(conv)
    db.commit()
    return conv


def _save_turn(db: Session, conv: Conversation, body: ChatIn, result: AgentResult) -> None:
    db.add(ChatMessage(conversation_id=conv.id, role="user", content=body.message))
    db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=result.reply,
                       meta={"request_id": result.request_id, "profile": result.profile,
                             "tools": [t["tool"] for t in result.tool_calls]}))
    db.commit()


def run_chat(db: Session, user: User, body: ChatIn, on_event=None) -> dict[str, Any]:
    if body.profile:
        reg = get_registry()
        if body.profile not in reg.profiles:
            raise HTTPException(400, f"unknown profile '{body.profile}'")
    conv = _conversation(db, user, body.conversation_id)
    ctx = tool_context(db, user, origin="agent")
    result = Agent().run(ctx, body.message, history=_history(db, conv.id), profile=body.profile,
                         language=body.language, on_event=on_event)
    _save_turn(db, conv, body, result)
    log_interaction(result, body.message, business_id=user.business_id, tool_results=result.tool_outputs)
    out = result.as_dict()
    out.pop("tool_outputs", None)  # internal (dataset); the UI gets traces instead
    out["conversation_id"] = conv.id
    out["interaction_id"] = result.request_id
    return out


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    return run_chat(db, user, body)


@router.post("/chat/stream")
def chat_stream(body: ChatIn, user: User = Depends(current_user)) -> StreamingResponse:
    """Server-sent events: `tool` events as each tool finishes, then `delta` chunks of the reply,
    then `done` with the full result (traces, pending confirmations, grounding)."""
    q: queue.Queue = queue.Queue()
    user_id = user.id

    def worker() -> None:
        db = SessionLocal()
        try:
            u = db.get(User, user_id)
            res = run_chat(db, u, body, on_event=lambda kind, payload: q.put((kind, payload)))
            q.put(("result", res))
        except HTTPException as e:
            q.put(("error", {"detail": e.detail}))
        except Exception as e:  # noqa: BLE001 - report, don't leak internals
            q.put(("error", {"detail": f"internal error: {type(e).__name__}"}))
        finally:
            db.close()
            q.put(("end", None))

    threading.Thread(target=worker, daemon=True).start()

    def events() -> Iterator[str]:
        while True:
            kind, payload = q.get()
            if kind == "end":
                break
            if kind == "result":
                words = payload["reply"].split(" ")
                for i in range(0, len(words), 6):
                    yield f"event: delta\ndata: {json.dumps({'text': ' '.join(words[i:i + 6]) + ' '}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/feedback")
def feedback(body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    log_feedback(body.interaction_id, body.rating, body.correction)
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id,
                 event_type="agent_decision", action="user_feedback",
                 inputs={"interaction_id": body.interaction_id, "rating": body.rating,
                         "has_correction": bool(body.correction)})
    return {"status": "recorded"}


# ----------------------------------------------------------------------------- tools
@router.get("/tools")
def list_tools(user: User = Depends(current_user)) -> list[dict[str, Any]]:
    load_all_tools()
    return [{"name": t.name, "tier": t.tier, "tier_name": TIER_NAMES[t.tier], "category": t.category,
             "description": t.description, "parameters": t.spec().parameters} for t in REGISTRY.values()]


@router.post("/tools/{name}")
def call_tool(name: str, body: ToolCallIn, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> dict[str, Any]:
    """Same pipeline the agent uses (validation, tiers, limits, confirmation, audit)."""
    ctx = tool_context(db, user, origin="api")
    out = execute(ctx, name, body.args)
    code = {"unknown_tool": 404, "invalid_args": 422, "denied": 403, "blocked": 403}.get(out.status)
    if code:
        raise HTTPException(code, {"status": out.status, "message": out.message})
    return out.as_dict()


# ----------------------------------------------------------------------------- audit
@router.get("/audit")
def audit_log(limit: int = 100, event_type: str = "", user: User = Depends(require_tier(1)),
              db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(AuditEvent).where(AuditEvent.business_id == user.business_id)
    if event_type:
        q = q.where(AuditEvent.event_type == event_type)
    rows = db.scalars(q.order_by(AuditEvent.id.desc()).limit(min(limit, 500))).all()
    return [audit.to_dict(e) for e in rows]


@router.get("/audit/verify")
def audit_verify(user: User = Depends(require_tier(1)), db: Session = Depends(get_db)) -> dict[str, Any]:
    return audit.verify_chain(db)
