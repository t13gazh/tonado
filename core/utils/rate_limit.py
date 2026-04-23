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


# Generic GET/HEAD/OPTIONS are exempt: the frontend polls /api/player/state
# and /api/system/health multiple times per second, and the SPA/static
# routes also flow through here. Putting polling GETs into the 100/min
# default would break the UI. Individual GETs that are expensive
# (currently only /api/system/update/check, which does a git fetch) are
# pulled out of the exempt set explicitly below.
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

# F1 (security audit): /api/system/update/check is a GET but does a
# `git fetch` on every call (network + SD-card writes). Pulling it out
# of the generic GET exempt so a `while true; curl .../update/check`
# loop can't wear out the SD card and spike CPU. Parent-tier auth
# alone isn't enough — a compromised LAN device with a valid token
# would hit the same problem.
_UPDATE_CHECK_PATH = "/api/system/update/check"

# Sleep-timer writes are not security-critical but the pill button is
# right next to a child's thumb — without its own bucket a single IP
# can pop 100 writes/min into the log. 20/min still allows parent-app
# spam-tap plus normal start/extend/cancel cycles.
#
# Exact path list (analogous to _LOGIN_PATH / _RESTORE_PATH) so future
# sibling routes like `/sleep-timer-history` don't silently inherit this
# bucket by prefix match. Add new sleep-timer write routes here explicitly.
# GET /sleep-timer is exempt via _SAFE_METHODS.
_SLEEP_TIMER_PATHS = frozenset({
    "/api/auth/sleep-timer",          # POST start, DELETE cancel
    "/api/auth/sleep-timer/extend",   # POST extend
})


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
        sleep_timer_limit: int = 20,
        sleep_timer_window: int = 60,
        update_check_limit: int = 6,
        update_check_window: int = 60,
    ) -> None:
        super().__init__(app)
        self._default = (default_limit, default_window)
        self._upload = (upload_limit, upload_window)
        self._login = (login_limit, login_window)
        self._restore = (restore_limit, restore_window)
        self._sleep_timer = (sleep_timer_limit, sleep_timer_window)
        self._update_check = (update_check_limit, update_check_window)
        self._buckets: dict[tuple[str, str], list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # F1: /api/system/update/check is a GET but triggers `git fetch`.
        # Check BEFORE the generic GET exempt so it can't slip through.
        # Normalise trailing slash so `/api/system/update/check/` can't
        # bypass the bucket by falling through into the GET exempt.
        if path.rstrip("/") == _UPDATE_CHECK_PATH and request.method in ("GET", "HEAD"):
            bucket_name = "update_check"
            limit, window = self._update_check
            return await self._enforce(request, bucket_name, limit, window, call_next)

        if request.method in _SAFE_METHODS:
            return await call_next(request)
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
        elif path in _SLEEP_TIMER_PATHS:
            bucket_name = "sleep_timer"
            limit, window = self._sleep_timer
        else:
            bucket_name = "default"
            limit, window = self._default

        return await self._enforce(request, bucket_name, limit, window, call_next)

    async def _enforce(
        self,
        request: Request,
        bucket_name: str,
        limit: int,
        window: int,
        call_next,
    ) -> Response:
        """Apply the sliding-window check for a single bucket."""
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
                bucket_name,
                limit,
                window,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Zu viele Anfragen"},
            )

        bucket.append(now)
        return await call_next(request)
