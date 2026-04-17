"""Captive portal service for first-boot WiFi setup.

Creates a temporary WiFi access point (AP) so the user can connect
with their smartphone and configure the real WiFi network via the
setup wizard.

Uses hostapd for AP mode and dnsmasq for DHCP + DNS redirect.
"""

import asyncio
import logging
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from core.services.base import BaseService
from core.services.config_service import ConfigService
from core.utils.subprocess import async_run

logger = logging.getLogger(__name__)

_HOSTAPD_CONF = """\
interface=wlan0
driver=nl80211
ssid={ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase={password}
"""

_DNSMASQ_CONF = """\
interface=wlan0
bind-interfaces
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
address=/#/192.168.4.1
"""

AP_SSID_PREFIX = "Tonado-Setup"
CONFIG_KEY_PASSWORD = "captive_portal.ap_password"
CONFIG_KEY_TIMEOUT = "captive_portal.timeout_minutes"
DEFAULT_TIMEOUT_MINUTES = 30
MIN_PASSWORD_LENGTH = 10


class CaptivePortalService(BaseService):
    """Manages the captive portal AP for first-boot WiFi configuration."""

    def __init__(
        self,
        ssid: str | None = None,
        config_service: ConfigService | None = None,
    ) -> None:
        super().__init__()
        self._ssid = ssid or f"{AP_SSID_PREFIX}"
        self._config = config_service
        self._hostapd_conf = Path("/tmp/tonado-hostapd.conf")
        self._dnsmasq_conf = Path("/tmp/tonado-dnsmasq.conf")
        self._active = False
        self._hostapd_proc: asyncio.subprocess.Process | None = None
        self._dnsmasq_proc: asyncio.subprocess.Process | None = None
        self._password: str = ""
        self._timeout_seconds: int = DEFAULT_TIMEOUT_MINUTES * 60
        self._timeout_task: asyncio.Task[None] | None = None
        self._started_at: float | None = None

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
        }

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

    async def _load_timeout_seconds(self) -> int:
        if self._config is None:
            return DEFAULT_TIMEOUT_MINUTES * 60
        value = await self._config.get(CONFIG_KEY_TIMEOUT)
        try:
            minutes = float(value) if value is not None else DEFAULT_TIMEOUT_MINUTES
        except (TypeError, ValueError):
            minutes = DEFAULT_TIMEOUT_MINUTES
        return max(1, int(minutes * 60))

    async def start(self) -> bool:
        """Start the captive portal AP.

        Returns True if successfully started, False if prerequisites missing.
        """
        if self._active:
            logger.warning("Captive portal already active")
            return True

        # Check prerequisites
        if not shutil.which("hostapd") or not shutil.which("dnsmasq"):
            logger.warning(
                "hostapd or dnsmasq not installed — captive portal unavailable. "
                "Install with: sudo apt install hostapd dnsmasq"
            )
            return False

        self._password = await self._load_or_generate_password()
        self._timeout_seconds = await self._load_timeout_seconds()

        try:
            # Stop any existing WiFi connection
            await self._run("nmcli", "device", "disconnect", "wlan0")

            # Configure static IP for AP
            await self._run(
                "ip", "addr", "flush", "dev", "wlan0",
            )
            await self._run(
                "ip", "addr", "add", "192.168.4.1/24", "dev", "wlan0",
            )
            await self._run("ip", "link", "set", "wlan0", "up")

            # Write config files
            self._hostapd_conf.write_text(
                _HOSTAPD_CONF.format(ssid=self._ssid, password=self._password)
            )
            self._dnsmasq_conf.write_text(_DNSMASQ_CONF)

            # Start hostapd
            self._hostapd_proc = await asyncio.create_subprocess_exec(
                "hostapd", str(self._hostapd_conf),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Start dnsmasq
            self._dnsmasq_proc = await asyncio.create_subprocess_exec(
                "dnsmasq", "-C", str(self._dnsmasq_conf), "--no-daemon",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Brief wait to check if processes started successfully
            await asyncio.sleep(1)
            if self._hostapd_proc.returncode is not None:
                logger.error("hostapd failed to start")
                await self.stop()
                return False

            self._active = True
            self._started_at = time.monotonic()
            logger.warning(
                "Captive portal started: SSID=%s password=%s timeout=%dmin ip=192.168.4.1",
                self._ssid,
                self._password,
                self._timeout_seconds // 60,
            )
            self._timeout_task = asyncio.create_task(self._auto_timeout())
            return True

        except Exception as e:
            logger.error("Failed to start captive portal: %s", e)
            await self.stop()
            return False

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
        """Stop the captive portal and restore normal WiFi."""
        if self._timeout_task is not None and not self._timeout_task.done():
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except (asyncio.CancelledError, Exception):
                pass
        self._timeout_task = None

        if self._hostapd_proc and self._hostapd_proc.returncode is None:
            self._hostapd_proc.terminate()
            await self._hostapd_proc.wait()

        if self._dnsmasq_proc and self._dnsmasq_proc.returncode is None:
            self._dnsmasq_proc.terminate()
            await self._dnsmasq_proc.wait()

        # Clean up config files
        self._hostapd_conf.unlink(missing_ok=True)
        self._dnsmasq_conf.unlink(missing_ok=True)

        # Restore wlan0
        await self._run("ip", "addr", "flush", "dev", "wlan0")

        # Restart NetworkManager if available
        if shutil.which("nmcli"):
            await self._run("nmcli", "device", "set", "wlan0", "managed", "yes")

        self._active = False
        self._started_at = None
        self._hostapd_proc = None
        self._dnsmasq_proc = None
        logger.info("Captive portal stopped")

    @staticmethod
    async def _run(*cmd: str) -> int:
        """Run a system command, suppressing errors."""
        rc, _, _ = await async_run(list(cmd))
        return rc
