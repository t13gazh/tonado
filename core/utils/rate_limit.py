"""Lightweight in-memory per-IP rate limit middleware.

Sliding window: each client IP keeps a list of request timestamps; old
entries are discarded on every call. GET/HEAD/OPTIONS are exempt (they
either serve the SPA or query read-only state) and the long-lived
audio stream proxy is skipped explicitly. Upload paths get a much
stricter bucket because they accept 500 MB bodies.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.utils.client_ip import extract_client_ip

logger = logging.getLogger(__name__)


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT_PREFIXES = ("/api/player/stream",)
_UPLOAD_PREFIX = "/api/library/upload"

# Expensive endpoints get their own tiny buckets so a single IP can't
# starve the box with PBKDF2 logins (~100k iterations) or large
# restore-payload parses (up to 10 MB JSON). The existing per-account
# login lockout catches wrong PINs; this limit also catches right-PIN
# hammering that would still burn CPU on a Pi Zero W.
_LOGIN_PATH = "/api/auth/login"
_RESTORE_PATH = "/api/system/restore"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        default_limit: int = 100,
        default_window: int = 60,
        upload_limit: int = 5,
        upload_window: int = 60,
        login_limit: int = 5,
        login_window: int = 60,
        restore_limit: int = 3,
        restore_window: int = 60,
    ) -> None:
        super().__init__(app)
        self._default = (default_limit, default_window)
        self._upload = (upload_limit, upload_window)
        self._login = (login_limit, login_window)
        self._restore = (restore_limit, restore_window)
        self._buckets: dict[tuple[str, str], list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Order matters: login and restore have their own tighter limits
        # and must not fall through to the generic 100/min default.
        if path == _LOGIN_PATH:
            bucket_name = "login"
            limit, window = self._login
        elif path == _RESTORE_PATH:
            bucket_name = "restore"
            limit, window = self._restore
        elif path.startswith(_UPLOAD_PREFIX):
            bucket_name = "upload"
            limit, window = self._upload
        else:
            bucket_name = "default"
            limit, window = self._default

        bucket_key = (extract_client_ip(request), bucket_name)

        now = time.monotonic()
        bucket = self._buckets[bucket_key]
        cutoff = now - window
        # Trim in-place so the list doesn't grow without bound
        bucket[:] = [t for t in bucket if t > cutoff]

        if len(bucket) >= limit:
            logger.warning(
                "Rate limit hit: ip=%s bucket=%s limit=%d window=%ds",
                bucket_key[0],
                bucket_key[1],
                limit,
                window,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
            )

        bucket.append(now)
        return await call_next(request)
