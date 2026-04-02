"""Setup wizard and system management API routes."""

import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.dependencies import (
    get_auth_service,
    get_captive_portal,
    get_setup_wizard,
    get_wifi_service,
    require_tier,
)
from core.services.auth_service import AuthService, AuthTier
from core.services.captive_portal import CaptivePortalService
from core.services.setup_wizard import SetupWizard
from core.services.wifi_service import WifiService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])


# --- Setup guard ---


def _require_setup_incomplete(wizard: SetupWizard) -> None:
    """Block setup endpoints after setup has been completed.

    Returns 403 so the frontend knows the setup is done and cannot be re-run
    (use /api/setup/reset with expert auth to re-enable).
    """
    if wizard.is_complete:
        raise HTTPException(403, "Setup already completed. Use reset endpoint to re-run.")


# --- Setup wizard ---


@router.get("/status")
async def setup_status(wizard: SetupWizard = Depends(get_setup_wizard)) -> dict:
    return wizard.status()


@router.post("/detect-hardware")
async def detect_hardware(wizard: SetupWizard = Depends(get_setup_wizard)) -> dict:
    _require_setup_incomplete(wizard)
    hw = await wizard.detect_hardware()
    return hw.to_dict()


class WifiConnectRequest(BaseModel):
    ssid: str
    password: str = ""


@router.post("/wifi/connect")
async def wifi_connect(
    req: WifiConnectRequest,
    wizard: SetupWizard = Depends(get_setup_wizard),
) -> dict:
    _require_setup_incomplete(wizard)
    return await wizard.setup_wifi(req.ssid, req.password)


@router.get("/wifi/scan")
async def wifi_scan(wifi: WifiService = Depends(get_wifi_service)) -> list[dict]:
    networks = await wifi.scan()
    return [asdict(n) for n in networks]


@router.get("/wifi/status")
async def wifi_status(wifi: WifiService = Depends(get_wifi_service)) -> dict:
    status = await wifi.status()
    return asdict(status)


class AudioSelectRequest(BaseModel):
    device: str


@router.post("/audio")
async def setup_audio(
    req: AudioSelectRequest,
    wizard: SetupWizard = Depends(get_setup_wizard),
) -> dict:
    _require_setup_incomplete(wizard)
    return await wizard.setup_audio(req.device)


@router.post("/test-audio")
async def test_audio() -> dict:
    """Play a short test tone through the current audio output via aplay."""
    test_file = Path(__file__).resolve().parent.parent.parent / "assets" / "test-tone.wav"
    if not test_file.exists():
        raise HTTPException(404, "Test tone file not found")
    try:
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "aplay", str(test_file),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode().strip() if stderr else "aplay failed")
        return {"success": True}
    except Exception as e:
        logger.warning("Test audio playback failed: %s", e)
        raise HTTPException(500, "Ton konnte nicht abgespielt werden")


@router.post("/buttons-done")
async def buttons_done(wizard: SetupWizard = Depends(get_setup_wizard)) -> dict:
    _require_setup_incomplete(wizard)
    return await wizard.setup_buttons([])  # Buttons saved via /api/buttons/config


@router.post("/first-card-done")
async def first_card_done(wizard: SetupWizard = Depends(get_setup_wizard)) -> dict:
    _require_setup_incomplete(wizard)
    return await wizard.complete_first_card()


@router.post("/complete")
async def complete_setup(
    wizard: SetupWizard = Depends(get_setup_wizard),
    portal: CaptivePortalService = Depends(get_captive_portal),
) -> dict:
    _require_setup_incomplete(wizard)
    result = await wizard.complete_setup()
    # Stop captive portal if active
    if portal.active:
        await portal.stop()
    return result


@router.post("/reset")
async def reset_setup(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    wizard: SetupWizard = Depends(get_setup_wizard),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    await wizard.reset()
    return {"status": "ok"}


# --- Captive portal ---


@router.get("/portal/status")
async def portal_status(portal: CaptivePortalService = Depends(get_captive_portal)) -> dict:
    return portal.status()


@router.post("/portal/start")
async def portal_start(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    portal: CaptivePortalService = Depends(get_captive_portal),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    success = await portal.start()
    if not success:
        raise HTTPException(500, "Failed to start captive portal")
    return portal.status()


@router.post("/portal/stop")
async def portal_stop(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    portal: CaptivePortalService = Depends(get_captive_portal),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    await portal.stop()
    return {"status": "ok"}
