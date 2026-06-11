"""Setup wizard and system management API routes."""

import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from core.dependencies import (
    get_auth_service,
    get_captive_portal,
    get_config_service,
    get_connectivity_monitor,
    get_setup_wizard,
    get_system_service,
    get_wifi_service,
    require_tier,
)
from core.services.auth_service import AuthService, AuthTier
from core.services.config_service import ConfigService
from core.services.system_service import SystemService
from core.services.captive_portal import (
    CONFIG_KEY_PASSWORD,
    CONFIG_KEY_SSID,
    MIN_PASSWORD_LENGTH,
    CaptivePortalService,
)
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
    wizard: SetupWizard = Depends(get_setup_wizard),
    monitor: ConnectivityMonitor = Depends(get_connectivity_monitor),
    config: ConfigService = Depends(get_config_service),
    system: SystemService = Depends(get_system_service),
) -> dict:
    """Finalize the ONLINE setup once the client has confirmed it can
    reach the box over the home WiFi.

    This endpoint is the SINGLE source of truth for online completion.
    The frontend's online CompleteStep calls it fire-and-forget (no-cors)
    and never calls /complete, so everything that makes the box "done"
    must happen here, in this order:

      1. 409 guard — if the marker already exists, setup is finished.
         409 is treated as success by the client; a retried no-cors call
         short-circuits here so it can't error-loop or double-reboot.
      2. Consume the one-shot probe token (403 if missing/expired). Token
         may arrive as a JSON body field or `?token=` query parameter —
         both survive captive-portal redirects differently.
      3. PIN gate + wizard/auth completion via wizard.complete_setup().
         It raises a German ValueError when the parent PIN is unset; we
         map that to 400 and finalize NOTHING (no marker, no teardown —
         the setup AP stays up so parents can still set a PIN). On
         success it sets SetupStep.COMPLETED and auth.set_setup_complete.
      4. AP teardown via finalize_setup_ap_teardown() (atomic marker
         FIRST, then stop/disable the AP unit). Power-loss-safe: a torn
         teardown still leaves the marker so a reboot skips the AP.
      5. Arm the ConnectivityMonitor for auto-fallback recovery — only
         when wifi.auto_fallback_enabled is truthy (default for online).
      6. Consume audio.reboot_pending and reboot LAST, after all state
         and the teardown are in place.

    Ordering rationale: completion state (step 3) is set BEFORE teardown
    (step 4) so a PIN-missing call short-circuits with the AP untouched.
    The marker write inside step 4 happens before the systemctl calls, so
    a teardown failure still leaves the marker — a subsequent retry hits
    the 409 guard and returns success instead of re-running anything.

    Returns 409 if already finalized (client treats as success), 403 on a
    bad token, 400 if the parent PIN is missing, 500 if the AP teardown
    fails partway.
    """
    if WifiService.SETUP_COMPLETE_MARKER.exists():
        raise HTTPException(409, "Setup wurde bereits abgeschlossen.")

    supplied = req.token or token
    if not consume_confirm_token(supplied):
        raise HTTPException(
            403,
            "Ungültiges oder abgelaufenes Token. Bitte WLAN-Test erneut ausführen.",
        )

    # PIN gate + wizard/auth completion FIRST. complete_setup() raises a
    # German ValueError when the parent PIN is unset (HIGH-2): we must not
    # finalize anything in that case — leave the setup AP up so parents can
    # still set a PIN. Setting COMPLETED state before teardown also means a
    # PIN-missing call leaves marker + AP untouched.
    try:
        await wizard.complete_setup()
    except ValueError as exc:
        # Curated German user message (see setup_wizard.complete_setup).
        raise HTTPException(400, str(exc)) from exc

    try:
        await wifi.finalize_setup_ap_teardown()
    except RuntimeError as exc:
        # Translate the teardown failure into an HTTP 500 so the client
        # knows the AP may still be up. The marker has been written
        # atomically earlier in finalize, so the system won't come back
        # up in AP mode after a reboot anyway. Wizard/auth state is already
        # COMPLETED; a retry hits the 409 guard and returns ok.
        raise HTTPException(500, str(exc)) from exc

    # Arm the auto-fallback monitor so home-WiFi loss later recovers into a
    # recovery AP. Held back in main.py during the wizard because the setup
    # AP and the monitor can't share wlan0. Only arm when auto-fallback is
    # enabled (default True online; offline persists it False).
    if await config.get("wifi.auto_fallback_enabled") and not monitor.is_running:
        await monitor.start()

    # Deferred audio-overlay reboot — LAST, after marker + teardown + state.
    # Consume + clear the flag so a retry / next boot can't loop-reboot.
    if await config.get("audio.reboot_pending"):
        await config.set("audio.reboot_pending", False)
        logger.info("Audio overlay reboot pending — rebooting box")
        await system.reboot()

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
async def wifi_scan(wifi: WifiService = Depends(get_wifi_service)) -> dict:
    """Return available WiFi networks plus the scan provenance.

    On a single-radio box the setup AP and a live scan can't coexist, so the
    list usually comes from the boot scan-cache (source="cache"). The frozen
    contract is {networks, source, scanned_at} — see WifiScanResult.
    """
    result = await wifi.scan_result()
    return {
        "networks": [asdict(n) for n in result.networks],
        "source": result.source,
        "scanned_at": result.scanned_at,
    }


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


@router.get("/recovery-wifi")
async def recovery_wifi_suggestion(
    wizard: SetupWizard = Depends(get_setup_wizard),
    portal: CaptivePortalService = Depends(get_captive_portal),
) -> dict:
    """Return a pre-filled suggestion for the recovery-WiFi credentials.

    The parent app shows these so the family can write them down before
    the recovery AP ever comes up (by then the phone is already offline).
    Reuses portal.credentials(), which generates + persists a strong
    password on first call and returns the configured SSID (default
    "Tonado"). The parent can overwrite both via the POST endpoint.
    """
    _require_setup_incomplete(wizard)
    return await portal.credentials()


class RecoveryWifiRequest(BaseModel):
    ssid: str
    password: str


@router.post("/recovery-wifi")
async def save_recovery_wifi(
    req: RecoveryWifiRequest,
    wizard: SetupWizard = Depends(get_setup_wizard),
    portal: CaptivePortalService = Depends(get_captive_portal),
) -> dict:
    """Validate + persist the (possibly edited) recovery-WiFi credentials.

    Writes the captive-portal config keys the CaptivePortalService reads
    (captive_portal.ap_ssid / .ap_password) and advances the wizard past
    the recovery-WiFi step. Validation mirrors WPA2 constraints, but with a
    stricter 10-char password minimum (MIN_PASSWORD_LENGTH).
    """
    _require_setup_incomplete(wizard)

    ssid = req.ssid.strip()
    if not ssid:
        raise HTTPException(400, "Bitte gib einen Namen für das Notfall-WLAN ein.")
    if len(ssid) > 32:
        raise HTTPException(400, "Der WLAN-Name darf höchstens 32 Zeichen lang sein.")
    # SSID must be printable on a single line — no control chars / newlines
    # that would break hostapd's config or be impossible to type on a phone.
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in ssid):
        raise HTTPException(400, "Der WLAN-Name enthält ungültige Zeichen.")

    password = req.password
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            400,
            f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein.",
        )
    if len(password) > 63:
        # WPA2-PSK passphrase upper bound.
        raise HTTPException(400, "Das Passwort darf höchstens 63 Zeichen lang sein.")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in password):
        raise HTTPException(400, "Das Passwort enthält ungültige Zeichen.")

    await wizard._config.set(CONFIG_KEY_SSID, ssid)
    await wizard._config.set(CONFIG_KEY_PASSWORD, password)
    # Keep the live portal instance in sync so a recovery AP started later
    # in the same process uses the freshly chosen credentials immediately.
    portal._ssid = ssid
    portal._password = password

    return await wizard.mark_recovery_wifi_done()


class CompleteSetupRequest(BaseModel):
    # "online": the box has home WiFi — keep the legacy probe→confirm
    # teardown flow untouched. "offline": no home WiFi — swap the single
    # radio to a permanent secured AP. Defaults to "online" for back-compat
    # with any client that posts an empty body.
    mode: str = "online"


@router.post("/complete")
async def complete_setup(
    req: CompleteSetupRequest = Body(default_factory=CompleteSetupRequest),
    wizard: SetupWizard = Depends(get_setup_wizard),
    portal: CaptivePortalService = Depends(get_captive_portal),
    monitor: ConnectivityMonitor = Depends(get_connectivity_monitor),
    config: ConfigService = Depends(get_config_service),
    wifi: WifiService = Depends(get_wifi_service),
    system: SystemService = Depends(get_system_service),
) -> dict:
    mode = req.mode if req.mode in ("online", "offline") else "online"

    # FIX B: offline finalize is re-runnable. complete_setup() sets
    # is_complete=True at the top, so if the subsequent _complete_offline AP
    # swap fails (500), the normal _require_setup_incomplete guard would 403
    # a retry and strand the parent (recoverable only by reboot). Allow a
    # re-run when completion is recorded but the offline AP swap is not yet
    # in place (offline_mode set + no live portal) so the swap can be
    # re-driven idempotently. The healthy "already complete" guard is
    # otherwise unchanged.
    offline_retry = False
    if wizard.is_complete:
        offline_retry = (
            await config.get("wifi.offline_mode") is True
            and not portal.active
        )
        if not offline_retry:
            raise HTTPException(
                403, "Setup already completed. Use reset endpoint to re-run."
            )
        mode = "offline"

    if not wizard.is_complete:
        try:
            result = await wizard.complete_setup()
        except ValueError as e:
            # ValueError carries a curated German user message (see setup_wizard.complete_setup)
            raise HTTPException(400, str(e))
    else:
        # offline_retry: completion already recorded; re-drive the AP swap only.
        result = {"success": True}

    # Safety net (both modes): guarantee a recovery-AP password exists so the
    # AP is functional + retrievable via /portal/credentials even if the
    # recovery-WiFi wizard step was somehow bypassed. credentials() generates
    # + persists one only if missing, so a parent-chosen password is left
    # untouched.
    await portal.credentials()

    if mode == "offline":
        await _complete_offline(wizard, portal, config, wifi)
    else:
        await _complete_online(portal, monitor)

    # TASK 4: deferred audio-overlay reboot. Done LAST — after all state is
    # persisted and (offline) the AP swap is in place — so the box boots
    # straight into the finished state, and an offline box comes back up
    # self-hosting the AP via the main.py startup path.
    if await config.get("audio.reboot_pending"):
        await config.set("audio.reboot_pending", False)
        logger.info("Audio overlay reboot pending — rebooting box")
        await system.reboot()

    return result


async def _complete_online(
    portal: CaptivePortalService,
    monitor: ConnectivityMonitor,
) -> None:
    """Online completion helper for the /complete direct path.

    NOTE: the production online flow does NOT run through here. The
    frontend's online CompleteStep finalizes via /confirm-complete
    (fire-and-forget no-cors), which is now the single online-completion
    authority — it drives wizard/auth completion, the AP teardown, monitor
    arming and the deferred audio reboot itself (see confirm_complete).

    This helper only runs when something calls POST /complete with mode
    "online" directly (e.g. tests or a legacy client). It stops a live
    portal instance and arms the auto-fallback monitor — a best-effort
    superset of confirm-complete's monitor step, kept idempotent so the two
    paths never conflict. The real setup-AP teardown still flows through
    /confirm-complete + the probe token.
    """
    if portal.active:
        await portal.stop()
    # Arm the auto-fallback monitor. It was held back in main.py because the
    # setup-wizard portal and the monitor can't share wlan0.
    if not monitor.is_running:
        await monitor.start()


async def _complete_offline(
    wizard: SetupWizard,
    portal: CaptivePortalService,
    config: ConfigService,
    wifi: WifiService,
) -> None:
    """Offline completion — swap the single radio to a permanent secured AP.

    No home WiFi exists, so:
      1. Persist the offline flags. auto_fallback_enabled=False makes the
         ConnectivityMonitor a no-op even if something starts it, so we never
         drive GRACE→fallback on a box that has nowhere to fall back to.
      2. Write the .setup-complete marker + stop/disable the OPEN setup AP
         (finalize_offline_setup — marker FIRST so an interrupted swap still
         leaves a box that recovers via the boot self-host path).
      3. Bring up the SECURED recovery AP as owner="offline" (permanent, no
         auto-timeout) using the credentials the parents wrote down.

    The ConnectivityMonitor is deliberately NOT armed here.
    """
    await config.set("wifi.offline_mode", True)
    await config.set("wifi.auto_fallback_enabled", False)

    # If a setup-wizard-owned portal instance is live in-process, stop it
    # first so the owner re-tag below is clean. (The OPEN setup AP itself is a
    # systemd unit, torn down by finalize_offline_setup.)
    if portal.active:
        await portal.stop()

    try:
        await wifi.finalize_offline_setup()
    except RuntimeError as exc:
        # The marker is written; the box will recover on reboot via the boot
        # self-host path. Surface the partial swap so the UI can warn.
        raise HTTPException(500, str(exc)) from exc

    # Brief unavoidable single-radio outage happens here as the OPEN AP goes
    # down and the SECURED AP comes up. Sequence is marker-first (above) so an
    # interruption still leaves a recoverable box.
    started = await portal.start(owner="offline")
    if not started:
        # hostapd/dnsmasq missing or script failed. The box is now offline
        # with no AP — but the marker + offline_mode flag mean the next boot
        # will retry the self-host. Tell the caller.
        raise HTTPException(
            500,
            "Das Notfall-WLAN konnte nicht gestartet werden. "
            "Bitte starte die Box neu.",
        )


@router.post("/reset")
async def reset_setup(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    wizard: SetupWizard = Depends(get_setup_wizard),
    wifi: WifiService = Depends(get_wifi_service),
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
    # Clear the probe-failure lockout too — it lives in WifiService, so a
    # reset would otherwise leave a locked-out parent stuck until reboot.
    wifi.reset_probe_lockout()
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
