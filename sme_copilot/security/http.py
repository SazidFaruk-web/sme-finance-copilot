"""HTTP hardening: security headers and in-memory rate limiting middleware."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=(self)")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        else:  # UI files: revalidate every load (cheap 304 via ETag) so an updated app.js is never stale
            h.setdefault("Cache-Control", "no-cache")
        if request.url.scheme == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp


class RateLimiter:
    """Sliding-window limiter keyed by (client, bucket). Single-process; use Redis for scale-out."""

    def __init__(self):
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: tuple[str, str], limit: int, window: float = 60.0) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False, int(window - (now - q[0])) + 1
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, get_limits):
        super().__init__(app)
        self.get_limits = get_limits  # () -> (general_per_min, login_per_min)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            general, login = self.get_limits()
            client = request.client.host if request.client else "unknown"
            bucket, limit = ("login", login) if path in ("/api/auth/login", "/api/auth/signup") else ("api", general)
            ok, retry = limiter.allow((client, bucket), limit)
            if not ok:
                return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                    headers={"Retry-After": str(retry)})
        return await call_next(request)
