"""Client IP extraction honouring trusted reverse proxies.

Nginx on the same host proxies every request from 127.0.0.1, which
otherwise globalises rate-limit buckets. We only honour X-Forwarded-For
or X-Real-IP when the direct peer is loopback — spoofed headers from
untrusted clients are ignored.
"""

from fastapi import Request

_TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})


def extract_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if peer in _TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return peer
