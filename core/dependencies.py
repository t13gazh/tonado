"""Shared FastAPI dependencies for authentication and authorization."""

from fastapi import HTTPException, Request

from core.services.auth_service import AuthService, AuthTier


def get_token(request: Request) -> str | None:
    """Extract JWT token from Authorization header."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def require_tier(request: Request, tier: AuthTier, auth: AuthService | None) -> None:
    """Raise 403 if token doesn't grant access to the required tier.

    If auth is None (e.g. during first setup), access is allowed.
    """
    if auth is None:
        return
    token = get_token(request)
    if not auth.check_access(token, tier):
        raise HTTPException(403, "Access denied")
