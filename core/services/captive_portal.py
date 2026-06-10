"""Captive portal service for the runtime WiFi *recovery* AP.

Spins up a temporary WiFi access point so a phone can reconnect and
reconfigure WiFi when the box loses its known network (taken to grandma's,
in the car, …). Music keeps playing from the local library; this AP just
makes the app reachable again.

This is NOT the first-boot setup AP. That one is owned by systemd
(`tonado-ap.service` → `setup-ap.sh start open`) and is deliberately OPEN,
because the parents have no credentials yet. The recovery AP handled here is
WPA2 and uses the SSID + password the parents picked in the setup wizard.

All privileged network operations are delegated to `system/setup-ap.sh` via
`sudo -n`: this process runs as the unprivileged `tonado` user and must never
drive hostapd/dnsmasq/ip/nmcli itself. setup-ap.sh is the single source of
truth for bringing wlan0 up as an AP and handing it back to NetworkManager.
"""

import asyncio
import logging
import secrets
import shutil
import time
from typing import Any, Literal

from core.services.base import BaseService
from core.services.config_service import ConfigService
from core.utils.subprocess import async_run

logger = logging.getLogger(__name__)

PortalOwner = Literal["setup", "auto", "manual"]

# The single privileged AP mechanism. Every wlan0 mutation is delegated to it
# via sudo; see system/sudoers.d/tonado for the matching NOPASSWD grants.
SETUP_AP_SCRIPT = "/opt/tonado/system/setup-ap.sh"

AP_SSID_DEFAULT = "Tonado"
CONFIG_KEY_SSID = "captive_portal.ap_ssid"
CONFIG_KEY_PASSWORD = "captive_portal.ap_password"
CONFIG_KEY_TIMEOUT = "captive_portal.timeout_minutes"
DEFAULT_TIMEOUT_MINUTES = 30
MIN_PASSWORD_LENGTH = 10


class CaptivePortalService(BaseService):
    """Manages the runtime recovery AP. State (active/owner/timeout/creds)
    lives here; the actual wlan0 work is delegated to setup-ap.sh."""

    def __init__(
        self,
        ssid: str | None = None,
        config_service: ConfigService | None = None,
    ) -> None:
        super().__init__()
        self._ssid = ssid or AP_SSID_DEFAULT
        self._config = config_service
        self._active = False
        self._password: str = ""
        self._timeout_seconds: int = DEFAULT_TIMEOUT_MINUTES * 60
        self._timeout_task: asyncio.Task[None] | None = None
        self._started_at: float | None = None
        self._owner: PortalOwner | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def ssid(self) -> str:
        return self._ssid

    @property
    def ap_password(self) -> str:
        """Current AP password (exposed only to callers with service access)."""
        return self._password

    @property
    def owner(self) -> PortalOwner | None:
        """Who started the portal — used by ConnectivityMonitor to know
        whether it's allowed to stop it on recovery."""
        return self._owner

    def status(self) -> dict[str, Any]:
        seconds_until_timeout: int | None = None
        if self._active and self._started_at is not None:
            elapsed = time.monotonic() - self._started_at
            remaining = max(0, int(self._timeout_seconds - elapsed))
            seconds_until_timeout = remaining
        return {
            "active": self._active,
            "ssid": self._ssid,
            "ip": "192.168.4.1" if self._active else None,
            "password_available": bool(self._password),
            "seconds_until_timeout": seconds_until_timeout,
            "owner": self._owner,
        }

    async def _load_ssid(self) -> str:
        """Read the AP SSID from config, falling back to the default."""
        if self._config is not None:
            stored = await self._config.get(CONFIG_KEY_SSID)
            if isinstance(stored, str) and stored.strip():
                return stored.strip()
        return self._ssid

    async def _load_or_generate_password(self) -> str:
        """Read the AP password from config or generate + persist a new one."""
        if self._config is not None:
            stored = await self._config.get(CONFIG_KEY_PASSWORD)
            if isinstance(stored, str) and len(stored) >= MIN_PASSWORD_LENGTH:
                return stored
        password = secrets.token_urlsafe(10)  # ~13 chars, WPA2-compatible
        if self._config is not None:
            await self._config.set(CONFIG_KEY_PASSWORD, password)
        return password

    async def credentials(self) -> dict[str, str]:
        """Return the AP SSID + password so the parent UI can display them
        (and render the 'stick on the fridge' QR code) *before* the AP is
        actually up — otherwise they'd only learn the credentials when the
        app is already unreachable.
        """
        password = self._password or await self._load_or_generate_password()
        if not self._password:
            self._password = password
        ssid = await self._load_ssid()
        self._ssid = ssid
        return {"ssid": ssid, "password": password}

    async def _load_timeout_seconds(self) -> int:
        if self._config is None:
            return DEFAULT_TIMEOUT_MINUTES * 60
        value = await self._config.get(CONFIG_KEY_TIMEOUT)
        try:
            minutes = float(value) if value is not None else DEFAULT_TIMEOUT_MINUTES
        except (TypeError, ValueError):
            minutes = DEFAULT_TIMEOUT_MINUTES
        return max(1, int(minutes * 60))

    async def start(self, owner: PortalOwner = "manual") -> bool:
        """Start the recovery AP (WPA2) by delegating to setup-ap.sh.

        Returns True if successfully started, False if prerequisites are
        missing or the script failed.

        `owner` records who triggered the start: "setup", "auto"
        (ConnectivityMonitor fallback) or "manual" (expert endpoint).
        ConnectivityMonitor uses this to decide whether it may stop the
        portal on WiFi recovery — it must never stop one it did not start.
        """
        if self._active:
            logger.warning("Captive portal already active (owner=%s)", self._owner)
            return True

        # Prerequisites: setup-ap.sh needs these binaries to be present.
        if not shutil.which("hostapd") or not shutil.which("dnsmasq"):
            logger.warning(
                "hostapd or dnsmasq not installed — captive portal unavailable. "
                "Install with: sudo apt install hostapd dnsmasq"
            )
            return False

        self._password = await self._load_or_generate_password()
        self._ssid = await self._load_ssid()
        self._timeout_seconds = await self._load_timeout_seconds()

        rc = await self._run_ap("start", "secured", self._ssid, self._password)
        if rc != 0:
            logger.error("setup-ap.sh start failed (rc=%s) — recovery AP not up", rc)
            # Best-effort cleanup in case the script half-configured wlan0.
            await self.stop()
            return False

        self._active = True
        self._started_at = time.monotonic()
        self._owner = owner
        logger.warning(
            "Recovery AP started: owner=%s SSID=%s timeout=%dmin ip=192.168.4.1",
            owner,
            self._ssid,
            self._timeout_seconds // 60,
        )
        self._timeout_task = asyncio.create_task(self._auto_timeout())
        return True

    async def _auto_timeout(self) -> None:
        """Stop the portal once the configured timeout elapses."""
        try:
            await asyncio.sleep(self._timeout_seconds)
        except asyncio.CancelledError:
            return
        if self._active:
            logger.warning(
                "Captive portal auto-timeout reached after %d min, shutting down.",
                self._timeout_seconds // 60,
            )
            await self.stop()

    async def stop(self) -> None:
        """Stop the recovery AP and restore normal WiFi via setup-ap.sh."""
        if self._timeout_task is not None and not self._timeout_task.done():
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except (asyncio.CancelledError, Exception):
                pass
        self._timeout_task = None

        # `setup-ap.sh stop` is idempotent (pkill || true, managed yes) so it's
        # safe to call even if start() never fully brought the AP up.
        await self._run_ap("stop")

        self._active = False
        self._started_at = None
        self._owner = None
        logger.info("Captive portal stopped")

    @staticmethod
    async def _run_ap(*args: str) -> int:
        """Delegate a privileged AP operation to setup-ap.sh via sudo.

        Returns the script's exit code (async_run yields 1 if sudo or the
        script is missing — e.g. on a dev box — which we treat as failure
        without raising).
        """
        rc, _, stderr = await async_run(["sudo", "-n", SETUP_AP_SCRIPT, *args])
        if rc != 0 and stderr.strip():
            logger.debug("setup-ap.sh %s: %s", " ".join(args), stderr.strip())
        return rc
