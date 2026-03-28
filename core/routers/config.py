"""Config API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from core.schemas.config import ConfigSetRequest, ConfigValueResponse
from core.services.config_service import ConfigService

router = APIRouter(prefix="/api/config", tags=["config"])

# Keys allowed to be read via API even though they start with "auth."
_AUTH_ALLOWLIST = {"auth.parent_pin_set", "auth.expert_pin_set"}


def _is_sensitive(key: str) -> bool:
    """Check if a config key is sensitive and must not be exposed via API."""
    if key.startswith("auth.") and key not in _AUTH_ALLOWLIST:
        return True
    return False

_config: ConfigService | None = None


def init(config_service: ConfigService) -> None:
    global _config
    _config = config_service


def _get_service() -> ConfigService:
    if _config is None:
        raise HTTPException(503, "Config service not available")
    return _config


@router.get("/", response_model=dict[str, Any])
async def get_all() -> dict:
    all_config = await _get_service().get_all()
    return {k: v for k, v in all_config.items() if not _is_sensitive(k)}


@router.get("/{key}", response_model=ConfigValueResponse)
async def get_value(key: str) -> dict:
    if _is_sensitive(key):
        raise HTTPException(403, "Zugriff auf diese Einstellung nicht erlaubt")
    value = await _get_service().get(key)
    if value is None:
        raise HTTPException(404, "Einstellung nicht gefunden")
    return {"key": key, "value": value}


@router.put("/")
async def set_value(req: ConfigSetRequest) -> dict:
    if _is_sensitive(req.key):
        raise HTTPException(403, "Diese Einstellung kann nicht direkt geändert werden")
    await _get_service().set(req.key, req.value)
    return {"status": "ok", "key": req.key, "value": req.value}


@router.delete("/{key}")
async def delete_value(key: str) -> dict:
    if _is_sensitive(key):
        raise HTTPException(403, "Diese Einstellung kann nicht gelöscht werden")
    deleted = await _get_service().delete(key)
    if not deleted:
        raise HTTPException(404, "Einstellung nicht gefunden")
    return {"status": "ok"}
