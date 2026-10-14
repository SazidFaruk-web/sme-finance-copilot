"""Authentication: bcrypt password hashing, opaque session tokens, lockout."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.config import get_settings
from sme_copilot.models import AuthSession, User, utcnow

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
ROLES = ("owner", "accountant", "viewer")


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    rounds = 4 if get_settings().app_env == "test" else 12  # fast hashes only in the test suite
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode())
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(session: Session, username: str, password: str) -> User:
    user = session.scalar(select(User).where(User.username == username.strip().lower()))
    now = utcnow()
    # Same error for unknown user and wrong password (no user enumeration).
    if user is None or not user.is_active:
        bcrypt.checkpw(b"timing-equaliser", bcrypt.hashpw(b"x", bcrypt.gensalt(rounds=4)))
        raise AuthError("invalid username or password")
    if user.locked_until and user.locked_until > now:
        raise AuthError("account temporarily locked after repeated failed logins; try again later")
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_logins = 0
        session.commit()
        raise AuthError("invalid username or password")
    user.failed_logins = 0
    user.locked_until = None
    session.commit()
    return user


def create_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(AuthSession(user_id=user.id, token_hash=_token_hash(token),
                            expires_at=utcnow() + timedelta(minutes=get_settings().session_ttl_minutes)))
    session.commit()
    return token


def resolve_token(session: Session, token: str) -> User | None:
    if not token:
        return None
    s = session.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if s is None or s.revoked or s.expires_at < utcnow():
        return None
    user = session.get(User, s.user_id)
    return user if user and user.is_active else None


def revoke_token(session: Session, token: str) -> None:
    s = session.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if s:
        s.revoked = True
        session.commit()


def create_user(session: Session, business_id: int, username: str, password: str, role: str,
                full_name: str = "") -> User:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    u = User(business_id=business_id, username=username.strip().lower(), password_hash=hash_password(password),
             role=role, full_name=full_name)
    session.add(u)
    session.flush()
    return u
