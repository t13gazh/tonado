"""Captive portal service for first-boot WiFi setup.

Creates a temporary WiFi access point (AP) so the user can connect
with their smartphone and configure the real WiFi network via the
setup wizard.

Uses hostapd for AP mode and dnsmasq for DHCP + DNS redirect.
"""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from core.services.base import BaseService
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
# No password — open network for easy setup
"""

_DNSMASQ_CONF = """\
interface=wlan0
bind-interfaces
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
address=/#/192.168.4.1
"""

AP_SSID_PREFIX = "Tonado-Setup"


class CaptivePortalService(BaseService):
    """Manages the captive portal AP for first-boot WiFi configuration."""

    def __init__(self, ssid: str | None = None) -> None:
        super().__init__()
        self._ssid = ssid or f"{AP_SSID_PREFIX}"
        self._hostapd_conf = Path("/tmp/tonado-hostapd.conf")
        self._dnsmasq_conf = Path("/tmp/tonado-dnsmasq.conf")
        self._active = False
        self._hostapd_proc: asyncio.subprocess.Process | None = None
        self._dnsmasq_proc: asyncio.subprocess.Process | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def ssid(self) -> str:
        return self._ssid

    def status(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "ssid": self._ssid,
            "ip": "192.168.4.1" if self._active else None,
        }

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
                _HOSTAPD_CONF.format(ssid=self._ssid)
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
            logger.info("Captive portal started: SSID='%s', IP=192.168.4.1", self._ssid)
            return True

        except Exception as e:
            logger.error("Failed to start captive portal: %s", e)
            await self.stop()
            return False

    async def stop(self) -> None:
        """Stop the captive portal and restore normal WiFi."""
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
        self._hostapd_proc = None
        self._dnsmasq_proc = None
        logger.info("Captive portal stopped")

    @staticmethod
    async def _run(*cmd: str) -> int:
        """Run a system command, suppressing errors."""
        rc, _, _ = await async_run(list(cmd))
        return rc
