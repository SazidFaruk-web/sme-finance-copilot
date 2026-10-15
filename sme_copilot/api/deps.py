"""FastAPI dependencies: DB session, authentication, roles, tool context."""
from __future__ import annotations

import hmac
import uuid
from datetime import date

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from sme_copilot.agent.toolkit import ToolContext
from sme_copilot.config import get_settings
from sme_copilot.db import get_db
from sme_copilot.models import Business, User
from sme_copilot.security import audit
from sme_copilot.security.auth import resolve_token, verify_password
from sme_copilot.security.permissions import ROLE_MAX_TIER, local_today


def as_of_today() -> date:
    s = get_settings().as_of_date
    return date.fromisoformat(s) if s else local_today()


SESSION_COOKIE = "smec_session"  # HttpOnly: page scripts cannot read the session token
CSRF_COOKIE = "smec_csrf"  # readable by the page; echoed in X-CSRF-Token (double-submit)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def bearer_token(request: Request, authorization: str = Header(default="")) -> str:
    """Bearer header (API clients, tests) or the HttpOnly cookie (browser). Cookie-authenticated writes must
    carry X-CSRF-Token equal to the CSRF cookie, which another site can neither read nor set."""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    token = request.cookies.get(SESSION_COOKIE, "")
    if token and request.method not in SAFE_METHODS:
        sent, expected = request.headers.get("x-csrf-token", ""), request.cookies.get(CSRF_COOKIE, "")
        if not expected or not hmac.compare_digest(sent, expected):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF check failed")
    return token


def current_user(token: str = Depends(bearer_token), db: Session = Depends(get_db)) -> User:
    user = resolve_token(db, token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require_tier(tier: int):
    def dep(user: User = Depends(current_user)) -> User:
        if ROLE_MAX_TIER.get(user.role, -1) < tier:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"role '{user.role}' cannot perform tier-{tier} actions")
        return user
    return dep


def require_owner(user: User = Depends(current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    return user


def step_up(db: Session, user: User, password: str | None, *, action: str, amount: float | None = None) -> None:
    """Re-authenticate for large payments/deletes. Failures are audited and return a machine-readable code."""
    if password and verify_password(password, user.password_hash):
        return
    audit.record(db, actor=user.username, actor_role=user.role, business_id=user.business_id, event_type="security",
                 action="step_up_failed", inputs={"for": action, "amount": amount}, confirmation_status="rejected")
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        {"code": "step_up_required", "message": "Re-enter your password to confirm this action."})


def tool_context(db: Session, user: User, origin: str = "api") -> ToolContext:
    business = db.get(Business, user.business_id)
    if business is None:
        raise HTTPException(404, "business not found")
    return ToolContext(session=db, business=business, user=user, as_of=as_of_today(),
                       request_id=uuid.uuid4().hex[:16], origin=origin)
