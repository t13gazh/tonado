"""GPIO button configuration and scanning API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.dependencies import (
    get_auth_service,
    get_button_service,
    get_hardware_detector,
    require_tier,
)
from core.hardware.detect import get_free_gpios
from core.hardware.gpio_buttons import (
    ButtonAction,
    ButtonConfig,
    MockGpioButtonScanner,
)
from core.services.auth_service import AuthService, AuthTier
from core.services.button_service import ButtonService
from core.services.hardware_detector import HardwareDetector

router = APIRouter(prefix="/api/buttons", tags=["buttons"])


# --- Schemas ---


class ButtonConfigItem(BaseModel):
    action: str  # ButtonAction value
    gpio: int


class ButtonsConfigRequest(BaseModel):
    buttons: list[ButtonConfigItem]


class ScanResultResponse(BaseModel):
    gpio: int | None = None
    detected: bool = False


class FreeGpiosResponse(BaseModel):
    gpios: list[int]


class MockPressRequest(BaseModel):
    gpio: int


# --- Endpoints ---


@router.get("/free-gpios")
async def free_gpios(
    detector: HardwareDetector = Depends(get_hardware_detector),
) -> FreeGpiosResponse:
    """Return list of GPIO pins available for buttons."""
    profile = detector.profile
    gpios = get_free_gpios(profile)
    return FreeGpiosResponse(gpios=gpios)


@router.get("/config")
async def get_config(
    svc: ButtonService = Depends(get_button_service),
) -> list[ButtonConfigItem]:
    """Return current button configuration."""
    return [
        ButtonConfigItem(action=b.action.value, gpio=b.gpio)
        for b in svc.buttons
    ]


@router.post("/config")
async def save_config(
    req: ButtonsConfigRequest,
    request: Request,
    svc: ButtonService = Depends(get_button_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Save button configuration (from wizard or settings). Requires PARENT auth."""
    require_tier(request, AuthTier.PARENT, auth)
    buttons = [
        ButtonConfig(action=ButtonAction(b.action), gpio=b.gpio)
        for b in req.buttons
    ]
    await svc.save_buttons(buttons)
    return {"success": True, "count": len(buttons)}


@router.delete("/config")
async def clear_config(
    request: Request,
    svc: ButtonService = Depends(get_button_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Remove all button configuration. Requires PARENT auth."""
    require_tier(request, AuthTier.PARENT, auth)
    await svc.clear_buttons()
    return {"success": True}


# --- Scanning ---


@router.post("/scan/start")
async def scan_start(
    svc: ButtonService = Depends(get_button_service),
    detector: HardwareDetector = Depends(get_hardware_detector),
) -> dict:
    """Start listening for a button press on any free GPIO."""
    profile = detector.profile
    free = get_free_gpios(profile)
    if not free:
        return {"success": False, "error": "Keine freien GPIO-Pins verfügbar"}
    try:
        await svc.start_scan(free)
    except RuntimeError as e:
        raise HTTPException(503, f"GPIO nicht verfügbar: {e}") from e
    return {"success": True, "watching": free}


@router.get("/scan/result")
async def scan_result(
    timeout: float = 15.0,
    svc: ButtonService = Depends(get_button_service),
) -> ScanResultResponse:
    """Wait for a button press. Returns the GPIO pin number."""
    result = await svc.get_scan_result(timeout=min(timeout, 30.0))
    return ScanResultResponse(gpio=result.gpio, detected=result.detected)


@router.post("/scan/stop")
async def scan_stop(
    svc: ButtonService = Depends(get_button_service),
) -> dict:
    """Stop the current scan."""
    await svc.stop_scan()
    return {"success": True}


# --- Test mode ---


@router.post("/test/start")
async def test_start(
    svc: ButtonService = Depends(get_button_service),
) -> dict:
    """Start test mode — presses are recorded for polling."""
    await svc.start_test()
    return {"success": True}


@router.get("/test/events")
async def test_events(
    svc: ButtonService = Depends(get_button_service),
) -> list[dict]:
    """Get pending test events (clears the queue)."""
    return svc.get_test_events()


@router.post("/test/stop")
async def test_stop(
    svc: ButtonService = Depends(get_button_service),
) -> dict:
    """Stop test mode."""
    await svc.stop_test()
    return {"success": True}


# --- Mock simulate (only available in mock mode) ---


@router.post("/mock/press")
async def mock_press(
    req: MockPressRequest,
    svc: ButtonService = Depends(get_button_service),
) -> dict:
    """Simulate a button press on a specific GPIO. Only works in mock mode."""
    scanner = svc._scanner
    if not isinstance(scanner, MockGpioButtonScanner):
        raise HTTPException(403, "Nur im Mock-Modus verfügbar")
    scanner.simulate_press(req.gpio)
    return {"success": True, "gpio": req.gpio}
