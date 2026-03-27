"""Config API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from core.schemas.config import ConfigSetRequest, ConfigValueResponse
from core.services.config_service import ConfigService

router = APIRouter(prefix="/api/config", tags=["config"])

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
    return await _get_service().get_all()


@router.get("/{key}", response_model=ConfigValueResponse)
async def get_value(key: str) -> dict:
    value = await _get_service().get(key)
    if value is None:
        raise HTTPException(404, "Einstellung nicht gefunden")
    return {"key": key, "value": value}


@router.put("/")
async def set_value(req: ConfigSetRequest) -> dict:
    await _get_service().set(req.key, req.value)
    return {"status": "ok", "key": req.key, "value": req.value}


@router.delete("/{key}")
async def delete_value(key: str) -> dict:
    deleted = await _get_service().delete(key)
    if not deleted:
        raise HTTPException(404, "Einstellung nicht gefunden")
    return {"status": "ok"}
