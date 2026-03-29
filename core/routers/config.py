"""Config API routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from core.dependencies import get_auth_service, get_config_service, require_tier
from core.schemas.config import ConfigSetRequest, ConfigValueResponse
from core.services.auth_service import AuthService, AuthTier
from core.services.config_service import ConfigService

router = APIRouter(prefix="/api/config", tags=["config"])

# Keys allowed to be read via API even though they start with "auth."
_AUTH_ALLOWLIST = {"auth.parent_pin_set", "auth.expert_pin_set"}


def _is_sensitive(key: str) -> bool:
    """Check if a config key is sensitive and must not be exposed via API."""
    if key.startswith("auth.") and key not in _AUTH_ALLOWLIST:
        return True
    return False


@router.get("/", response_model=dict[str, Any])
async def get_all(svc: ConfigService = Depends(get_config_service)) -> dict:
    all_config = await svc.get_all()
    return {k: v for k, v in all_config.items() if not _is_sensitive(k)}


@router.get("/{key}", response_model=ConfigValueResponse)
async def get_value(key: str, svc: ConfigService = Depends(get_config_service)) -> dict:
    if _is_sensitive(key):
        raise HTTPException(403, "Access to this setting not allowed")
    value = await svc.get(key)
    if value is None:
        raise HTTPException(404, "Setting not found")
    return {"key": key, "value": value}


@router.put("/")
async def set_value(
    request: Request,
    req: ConfigSetRequest,
    svc: ConfigService = Depends(get_config_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    if _is_sensitive(req.key):
        raise HTTPException(403, "This setting cannot be changed directly")
    await svc.set(req.key, req.value)
    return {"status": "ok", "key": req.key, "value": req.value}


@router.delete("/{key}")
async def delete_value(
    request: Request,
    key: str,
    svc: ConfigService = Depends(get_config_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    if _is_sensitive(key):
        raise HTTPException(403, "This setting cannot be deleted")
    deleted = await svc.delete(key)
    if not deleted:
        raise HTTPException(404, "Setting not found")
    return {"status": "ok"}
