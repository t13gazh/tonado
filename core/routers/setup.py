"""Setup wizard and system management API routes."""

import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from core.dependencies import (
    get_auth_service,
    get_captive_portal,
    get_connectivity_monitor,
    get_setup_wizard,
    get_wifi_service,
    require_tier,
)
from core.services.auth_service import AuthService, AuthTier
from core.services.captive_portal import CaptivePortalService
from core.services.connectivity_monitor import ConnectivityMonitor
from core.services.setup_wizard import SetupWizard
from core.services.wifi_service import (
    WifiService,
    clear_confirm_tokens,
    consume_confirm_token,
)

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
    wifi: WifiService = Depends(get_wifi_service),
) -> dict:
    """Probe the home WiFi without tearing the setup AP down.

    NOTE (pre-0.4 behaviour change): this endpoint used to immediately
    `nmcli connect` the home SSID as wlan0's active profile, which
    destroyed the setup AP the moment it started. A user who entered a
    wrong PSK would then be stranded with no way back into the wizard
    from their phone. We now route through `probe_home_wifi`, which
    creates a passive `autoconnect no` profile and brings it up
    explicitly — the AP stays in service. The returned `token` must be
    replayed to /api/setup/confirm-complete to actually finalize
    teardown.
    """
    _require_setup_incomplete(wizard)
    if WifiService.SETUP_COMPLETE_MARKER.exists():
        raise HTTPException(409, "Setup wurde bereits abgeschlossen.")
    result = await wifi.probe_home_wifi(req.ssid, req.password)
    if result.get("locked"):
        # Force a HTTP-429 so the frontend can surface the lockout
        # distinctly from a plain wrong-PSK response.
        raise HTTPException(429, result.get("error") or "Zu viele Fehlversuche.")
    # Surface SSID upfront so the wizard can persist it for the UI even
    # before the user has hit /confirm-complete.
    if result.get("ok"):
        await wizard._config.set("wifi.ssid", req.ssid)
    return result


class WifiTestRequest(BaseModel):
    ssid: str
    password: str = ""


@router.post("/test-wifi")
async def test_wifi(
    req: WifiTestRequest,
    wifi: WifiService = Depends(get_wifi_service),
) -> dict:
    """Probe a home WiFi without tearing down the setup AP.

    Returns {ok, error, ip, token}. A falsy `ok` lets the wizard keep the
    user in the setup AP so they can correct their input. On success the
    caller receives a one-shot `token` that must be echoed back to
    /api/setup/confirm-complete within ~10 minutes. `.setup-complete` is
    NOT written here — that happens in /confirm-complete after the
    client has confirmed reachability over the home WiFi.

    Returns 409 Conflict if setup has already been finalized previously,
    and 429 Too Many Requests when the probe is locked out after
    repeated wrong passwords.
    """
    if WifiService.SETUP_COMPLETE_MARKER.exists():
        raise HTTPException(409, "Setup wurde bereits abgeschlossen.")
    result = await wifi.probe_home_wifi(req.ssid, req.password)
    if result.get("locked"):
        raise HTTPException(429, result.get("error") or "Zu viele Fehlversuche.")
    return result


class ConfirmCompleteRequest(BaseModel):
    # Token issued by /test-wifi (or /wifi/connect) on a successful
    # probe. Kept optional so we can return a clean 403 explaining the
    # flow, rather than a Pydantic-422 that's harder for the UI to
    # distinguish from generic validation noise.
    token: str | None = None


@router.post("/confirm-complete")
async def confirm_complete(
    req: ConfirmCompleteRequest = Body(default_factory=ConfirmCompleteRequest),
    token: str | None = None,
    wifi: WifiService = Depends(get_wifi_service),
) -> dict:
    """Finalize the wizard once the client has confirmed it can reach
    the box over the home WiFi. Writes `.setup-complete`, stops and
    disables the setup AP, and removes the NM unmanaged override.

    Requires the one-shot token returned by /test-wifi (or the
    /wifi/connect probe path). Token may be passed as a JSON body field
    or as a `?token=` query parameter — accept both because the setup
    wizard lives on a captive-portal page where query strings sometimes
    survive redirects better than request bodies.

    Returns 409 Conflict if setup has already been finalized previously,
    403 if the token is missing, unknown or expired, 500 if the AP
    teardown itself fails partway.
    """
    if WifiService.SETUP_COMPLETE_MARKER.exists():
        raise HTTPException(409, "Setup wurde bereits abgeschlossen.")

    supplied = req.token or token
    if not consume_confirm_token(supplied):
        raise HTTPException(
            403,
            "Ungültiges oder abgelaufenes Token. Bitte WLAN-Test erneut ausführen.",
        )

    try:
        await wifi.finalize_setup_ap_teardown()
    except RuntimeError as exc:
        # Translate the teardown failure into an HTTP 500 so the client
        # knows the AP may still be up. The marker has been written
        # atomically earlier in finalize, so the system won't come back
        # up in AP mode after a reboot anyway.
        raise HTTPException(500, str(exc)) from exc
    return {"status": "ok"}


@router.post("/cancel-probe")
async def cancel_probe(
    wifi: WifiService = Depends(get_wifi_service),
) -> dict:
    """Drop any lingering home-WiFi probe profile.

    Called by the wizard when the user backs out of a probe (e.g. to
    retype a password). Idempotent — always returns `{"ok": True}`.
    Token registry is NOT touched; an outstanding token stays valid
    for its TTL unless a later successful probe issues a new one.
    """
    if WifiService.SETUP_COMPLETE_MARKER.exists():
        raise HTTPException(409, "Setup wurde bereits abgeschlossen.")
    return await wifi.cancel_probe()


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


@router.post("/pin-done")
async def pin_done(wizard: SetupWizard = Depends(get_setup_wizard)) -> dict:
    """Advance the wizard past the PIN step.

    The actual PIN-setting happens via /api/auth/pin; this endpoint
    only updates the wizard's own step state so the UI can proceed.
    """
    _require_setup_incomplete(wizard)
    return await wizard.mark_pin_setup_done()


@router.post("/complete")
async def complete_setup(
    wizard: SetupWizard = Depends(get_setup_wizard),
    portal: CaptivePortalService = Depends(get_captive_portal),
    monitor: ConnectivityMonitor = Depends(get_connectivity_monitor),
) -> dict:
    _require_setup_incomplete(wizard)
    try:
        result = await wizard.complete_setup()
    except ValueError as e:
        # ValueError carries a curated German user message (see setup_wizard.complete_setup)
        raise HTTPException(400, str(e))
    # Stop captive portal if active
    if portal.active:
        await portal.stop()
    # Now that setup is done, arm the auto-fallback monitor. It was held
    # back in main.py because the setup-wizard portal and the monitor can't
    # share wlan0.
    if not monitor.is_running:
        await monitor.start()
    return result


@router.post("/reset")
async def reset_setup(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    wizard: SetupWizard = Depends(get_setup_wizard),
) -> dict:
    """Restart the setup wizard.

    During onboarding, before any PIN exists, reset must be accessible
    without auth to avoid bricking a box whose owner got stuck mid-flow
    and has no expert credentials yet. Once EXPERT has a PIN, the
    endpoint is expert-only again — a completed box should never be
    wizard-reset by an opportunistic LAN caller.
    """
    # F12: if the expert tier has no PIN yet, we're still in onboarding
    # and reset is the only escape hatch from a stuck wizard.
    expert_pin_set = await auth.is_pin_set(AuthTier.EXPERT)
    if expert_pin_set:
        require_tier(request, AuthTier.EXPERT, auth)
    await wizard.reset()
    # Any pending confirm-tokens are now stale — the wizard will have
    # to probe fresh after reset.
    clear_confirm_tokens()
    return {"status": "ok"}


# --- Captive portal ---


@router.get("/portal/status")
async def portal_status(portal: CaptivePortalService = Depends(get_captive_portal)) -> dict:
    return portal.status()


@router.get("/portal/credentials")
async def portal_credentials(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    portal: CaptivePortalService = Depends(get_captive_portal),
) -> dict:
    """Return the AP SSID + password so the parent app can show them
    ahead of time — they're useless after the AP is up, since the phone
    would already be offline from the main WiFi."""
    require_tier(request, AuthTier.PARENT, auth)
    return await portal.credentials()


@router.post("/portal/start")
async def portal_start(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    portal: CaptivePortalService = Depends(get_captive_portal),
) -> dict:
    require_tier(request, AuthTier.EXPERT, auth)
    success = await portal.start(owner="manual")
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


# --- Connectivity monitor (auto-fallback AP) ---


@router.get("/connectivity/status")
async def connectivity_status(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    monitor: ConnectivityMonitor = Depends(get_connectivity_monitor),
) -> dict:
    """Current auto-fallback monitor state (for UI badge + debugging).

    PARENT-tier: the window counter is a recon signal on a LAN-only API,
    but there's no reason to gate it harder than sleep timer / volume.
    """
    require_tier(request, AuthTier.PARENT, auth)
    return {
        "running": monitor.is_running,
        **monitor.status(),
    }
