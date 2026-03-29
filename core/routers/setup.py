"""Setup wizard and system management API routes."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.dependencies import require_tier
from core.services.auth_service import AuthService, AuthTier
from core.services.captive_portal import CaptivePortalService
from core.services.setup_wizard import SetupWizard
from core.services.wifi_service import WifiService

router = APIRouter(prefix="/api/setup", tags=["setup"])

_wizard: SetupWizard | None = None
_wifi: WifiService | None = None
_captive_portal: CaptivePortalService | None = None
_auth: AuthService | None = None


def init(
    wizard: SetupWizard,
    wifi: WifiService,
    captive_portal: CaptivePortalService,
    auth_service: AuthService | None = None,
) -> None:
    global _wizard, _wifi, _captive_portal, _auth
    _wizard = wizard
    _wifi = wifi
    _captive_portal = captive_portal
    _auth = auth_service


def _get_wizard() -> SetupWizard:
    if _wizard is None:
        raise HTTPException(503, "Setup wizard not available")
    return _wizard


def _get_wifi() -> WifiService:
    if _wifi is None:
        raise HTTPException(503, "WiFi service not available")
    return _wifi



# --- Setup wizard ---


@router.get("/status")
async def setup_status() -> dict:
    return _get_wizard().status()


@router.post("/detect-hardware")
async def detect_hardware() -> dict:
    hw = await _get_wizard().detect_hardware()
    return hw.to_dict()


class WifiConnectRequest(BaseModel):
    ssid: str
    password: str = ""


@router.post("/wifi/connect")
async def wifi_connect(req: WifiConnectRequest) -> dict:
    return await _get_wizard().setup_wifi(req.ssid, req.password)


@router.get("/wifi/scan")
async def wifi_scan() -> list[dict]:
    networks = await _get_wifi().scan()
    return [n.to_dict() for n in networks]


@router.get("/wifi/status")
async def wifi_status() -> dict:
    status = await _get_wifi().status()
    return status.to_dict()


class AudioSelectRequest(BaseModel):
    device: str


@router.post("/audio")
async def setup_audio(req: AudioSelectRequest) -> dict:
    return await _get_wizard().setup_audio(req.device)


@router.post("/first-card-done")
async def first_card_done() -> dict:
    return await _get_wizard().complete_first_card()


@router.post("/complete")
async def complete_setup() -> dict:
    result = await _get_wizard().complete_setup()
    # Stop captive portal if active
    if _captive_portal and _captive_portal.active:
        await _captive_portal.stop()
    return result


@router.post("/reset")
async def reset_setup(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    await _get_wizard().reset()
    return {"status": "ok"}


# --- Captive portal ---


@router.get("/portal/status")
async def portal_status() -> dict:
    if _captive_portal is None:
        return {"active": False}
    return _captive_portal.status()


@router.post("/portal/start")
async def portal_start(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    if _captive_portal is None:
        raise HTTPException(503, "Captive portal not available")
    success = await _captive_portal.start()
    if not success:
        raise HTTPException(500, "Failed to start captive portal")
    return _captive_portal.status()


@router.post("/portal/stop")
async def portal_stop(request: Request) -> dict:
    require_tier(request, AuthTier.EXPERT, _auth)
    if _captive_portal is None:
        raise HTTPException(503, "Captive portal not available")
    await _captive_portal.stop()
    return {"status": "ok"}
