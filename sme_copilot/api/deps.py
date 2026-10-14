"""FastAPI dependencies: DB session, authentication, roles, tool context."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from sme_copilot.agent.toolkit import ToolContext
from sme_copilot.config import get_settings
from sme_copilot.db import get_db
from sme_copilot.models import Business, User
from sme_copilot.security.auth import resolve_token
from sme_copilot.security.permissions import ROLE_MAX_TIER, local_today


def as_of_today() -> date:
    s = get_settings().as_of_date
    return date.fromisoformat(s) if s else local_today()


def bearer_token(authorization: str = Header(default="")) -> str:
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


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


def tool_context(db: Session, user: User, origin: str = "api") -> ToolContext:
    business = db.get(Business, user.business_id)
    if business is None:
        raise HTTPException(404, "business not found")
    return ToolContext(session=db, business=business, user=user, as_of=as_of_today(),
                       request_id=uuid.uuid4().hex[:16], origin=origin)
