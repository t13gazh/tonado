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


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        default_limit: int = 100,
        default_window: int = 60,
        upload_limit: int = 5,
        upload_window: int = 60,
    ) -> None:
        super().__init__(app)
        self._default = (default_limit, default_window)
        self._upload = (upload_limit, upload_window)
        self._buckets: dict[tuple[str, str], list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        is_upload = path.startswith(_UPLOAD_PREFIX)
        limit, window = self._upload if is_upload else self._default
        bucket_key = (extract_client_ip(request), "upload" if is_upload else "default")

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
