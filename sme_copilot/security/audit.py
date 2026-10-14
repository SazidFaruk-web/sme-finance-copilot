"""Immutable, hash-chained audit log.

Each event stores ``prev_hash`` and ``hash = sha256(prev_hash || canonical_json(event))``.
Any edit or deletion of a past row breaks the chain, and ``verify_chain`` reports the first
broken link. On SQLite, triggers additionally reject UPDATE/DELETE at the storage layer
(see db.AUDIT_TRIGGERS). Inputs/results are PII-masked before storage.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.models import AuditEvent, utcnow

from .pii import mask_obj

GENESIS = "0" * 64
_lock = threading.Lock()


def _canonical(ev: dict[str, Any]) -> str:
    return json.dumps(ev, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _event_dict(e: AuditEvent) -> dict[str, Any]:
    return {
        "ts": e.ts.isoformat(timespec="microseconds") if isinstance(e.ts, datetime) else str(e.ts),
        "business_id": e.business_id, "actor": e.actor, "actor_role": e.actor_role, "event_type": e.event_type,
        "action": e.action, "tier": e.tier, "inputs": e.inputs, "result": e.result,
        "confirmation_status": e.confirmation_status, "request_id": e.request_id,
    }


def compute_hash(prev_hash: str, ev: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(ev)).encode("utf-8")).hexdigest()


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str, ensure_ascii=False))


def record(session: Session, *, actor: str, event_type: str, action: str, business_id: int | None = None,
           actor_role: str = "", tier: int | None = None, inputs: dict[str, Any] | None = None,
           result: dict[str, Any] | None = None, confirmation_status: str = "not_required",
           request_id: str = "", commit: bool = True) -> AuditEvent:
    """Append one event. Serialised with a process lock so the chain never forks."""
    with _lock:
        last = session.scalar(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1))
        prev = last.hash if last else GENESIS
        ev = AuditEvent(
            ts=utcnow(), business_id=business_id, actor=actor[:80], actor_role=actor_role, event_type=event_type,
            action=action[:80], tier=tier, inputs=_jsonable(mask_obj(inputs or {})),
            result=_jsonable(mask_obj(_truncate(result or {}))), confirmation_status=confirmation_status,
            request_id=request_id, prev_hash=prev, hash="")
        ev.hash = compute_hash(prev, _event_dict(ev))
        session.add(ev)
        session.flush()
        if commit:
            session.commit()
        return ev


def _truncate(obj: Any, max_items: int = 25, max_str: int = 600) -> Any:
    """Keep audit rows compact: long lists/strings are summarised, not dropped silently."""
    if isinstance(obj, dict):
        return {k: _truncate(v, max_items, max_str) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > max_items:
            return [_truncate(v, max_items, max_str) for v in obj[:max_items]] + [f"... {len(obj) - max_items} more"]
        return [_truncate(v, max_items, max_str) for v in obj]
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + "..."
    return obj


def verify_chain(session: Session) -> dict[str, Any]:
    prev = GENESIS
    count = 0
    # populate_existing: always re-read from storage, never trust objects cached in the session.
    for e in session.scalars(select(AuditEvent).order_by(AuditEvent.id).execution_options(populate_existing=True)):
        count += 1
        if e.prev_hash != prev:
            return {"ok": False, "events": count, "broken_at_id": e.id, "reason": "prev_hash mismatch"}
        if compute_hash(prev, _event_dict(e)) != e.hash:
            return {"ok": False, "events": count, "broken_at_id": e.id, "reason": "content hash mismatch"}
        prev = e.hash
    return {"ok": True, "events": count, "head": prev}


def to_dict(e: AuditEvent) -> dict[str, Any]:
    d = _event_dict(e)
    d.update({"id": e.id, "prev_hash": e.prev_hash, "hash": e.hash})
    return d
