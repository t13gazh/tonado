"""WiFi management service.

Manages WiFi connections via NetworkManager (nmcli) on the Pi.
Falls back to wpa_supplicant if NetworkManager is unavailable.
"""

import asyncio
import logging
import shutil
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WifiNetwork:
    """A detected WiFi network."""

    ssid: str
    signal: int  # 0-100
    security: str  # "open", "wpa", "wpa2", "wep"
    connected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ssid": self.ssid,
            "signal": self.signal,
            "security": self.security,
            "connected": self.connected,
        }


@dataclass
class WifiStatus:
    """Current WiFi connection status."""

    connected: bool = False
    ssid: str = ""
    ip_address: str = ""
    signal: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "ssid": self.ssid,
            "ip_address": self.ip_address,
            "signal": self.signal,
        }


class WifiService:
    """Manages WiFi connections on the Raspberry Pi."""

    def __init__(self) -> None:
        self._use_nmcli = shutil.which("nmcli") is not None
        self._mock = not self._use_nmcli and shutil.which("wpa_cli") is None

    async def start(self) -> None:
        if self._mock:
            logger.info("WiFi service started in mock mode (no nmcli/wpa_cli)")
        elif self._use_nmcli:
            logger.info("WiFi service started (NetworkManager)")
        else:
            logger.info("WiFi service started (wpa_supplicant)")

    async def scan(self) -> list[WifiNetwork]:
        """Scan for available WiFi networks."""
        if self._mock:
            return self._mock_scan()

        if self._use_nmcli:
            return await self._nmcli_scan()
        return await self._wpa_scan()

    async def connect(self, ssid: str, password: str = "") -> bool:
        """Connect to a WiFi network. Returns True on success."""
        if self._mock:
            logger.info("Mock: connecting to '%s'", ssid)
            return True

        if self._use_nmcli:
            return await self._nmcli_connect(ssid, password)
        return await self._wpa_connect(ssid, password)

    async def disconnect(self) -> bool:
        """Disconnect from current WiFi network."""
        if self._mock:
            return True

        if self._use_nmcli:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "device", "disconnect", "wlan0",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        return False

    async def status(self) -> WifiStatus:
        """Get current WiFi connection status."""
        if self._mock:
            return WifiStatus()

        if self._use_nmcli:
            return await self._nmcli_status()
        return await self._wpa_status()

    async def forget(self, ssid: str) -> bool:
        """Remove a saved WiFi network."""
        if self._mock:
            return True

        if self._use_nmcli:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "connection", "delete", ssid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        return False

    # --- NetworkManager (nmcli) implementation ---

    async def _nmcli_scan(self) -> list[WifiNetwork]:
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "device", "wifi", "list",
            "--rescan", "yes",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        networks: list[WifiNetwork] = []
        seen: set[str] = set()

        for line in stdout.decode().strip().splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)

            signal = int(parts[1]) if parts[1].isdigit() else 0
            security_raw = parts[2].strip().lower()
            connected = parts[3].strip().lower() == "yes"

            if "wpa2" in security_raw:
                security = "wpa2"
            elif "wpa" in security_raw:
                security = "wpa"
            elif "wep" in security_raw:
                security = "wep"
            elif security_raw == "" or security_raw == "--":
                security = "open"
            else:
                security = "wpa2"

            networks.append(WifiNetwork(
                ssid=ssid, signal=signal, security=security, connected=connected,
            ))

        networks.sort(key=lambda n: (-n.connected, -n.signal))
        return networks

    async def _nmcli_connect(self, ssid: str, password: str) -> bool:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        success = proc.returncode == 0

        if success:
            logger.info("Connected to WiFi: %s", ssid)
        else:
            logger.error("WiFi connection failed: %s", stderr.decode().strip())

        return success

    async def _nmcli_status(self) -> WifiStatus:
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS",
            "device", "show", "wlan0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        status = WifiStatus()
        for line in stdout.decode().strip().splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            if key == "GENERAL.CONNECTION" and value and value != "--":
                status.ssid = value
                status.connected = True
            elif key.startswith("IP4.ADDRESS"):
                status.ip_address = value.split("/")[0] if "/" in value else value

        # Get actual SSID and signal from wifi list (GENERAL.CONNECTION is the profile name)
        if status.connected:
            try:
                sig_proc = await asyncio.create_subprocess_exec(
                    "nmcli", "-t", "-f", "SSID,SIGNAL,ACTIVE", "device", "wifi", "list",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                sig_out, _ = await sig_proc.communicate()
                for sig_line in sig_out.decode().strip().splitlines():
                    parts = sig_line.split(":")
                    if len(parts) >= 3 and parts[2].strip() == "yes":
                        if parts[0].strip():
                            status.ssid = parts[0].strip()
                        status.signal = int(parts[1]) if parts[1].isdigit() else 0
                        break
            except Exception:
                pass

        return status

    # --- wpa_supplicant fallback ---

    async def _wpa_scan(self) -> list[WifiNetwork]:
        proc = await asyncio.create_subprocess_exec(
            "wpa_cli", "-i", "wlan0", "scan",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(2)  # Wait for scan to complete

        proc = await asyncio.create_subprocess_exec(
            "wpa_cli", "-i", "wlan0", "scan_results",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        networks: list[WifiNetwork] = []
        for line in stdout.decode().strip().splitlines()[1:]:  # Skip header
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            signal_dbm = int(parts[2]) if parts[2].lstrip("-").isdigit() else -100
            signal = max(0, min(100, 2 * (signal_dbm + 100)))
            flags = parts[3]
            ssid = parts[4]

            if "WPA2" in flags:
                security = "wpa2"
            elif "WPA" in flags:
                security = "wpa"
            elif "WEP" in flags:
                security = "wep"
            else:
                security = "open"

            networks.append(WifiNetwork(ssid=ssid, signal=signal, security=security))

        networks.sort(key=lambda n: -n.signal)
        return networks

    async def _wpa_connect(self, ssid: str, password: str) -> bool:
        # Add network
        proc = await asyncio.create_subprocess_exec(
            "wpa_cli", "-i", "wlan0", "add_network",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        network_id = stdout.decode().strip()

        # Set SSID
        await (await asyncio.create_subprocess_exec(
            "wpa_cli", "-i", "wlan0", "set_network", network_id, "ssid", f'"{ssid}"',
            stdout=asyncio.subprocess.PIPE,
        )).wait()

        # Set password or open
        if password:
            await (await asyncio.create_subprocess_exec(
                "wpa_cli", "-i", "wlan0", "set_network", network_id, "psk", f'"{password}"',
                stdout=asyncio.subprocess.PIPE,
            )).wait()
        else:
            await (await asyncio.create_subprocess_exec(
                "wpa_cli", "-i", "wlan0", "set_network", network_id, "key_mgmt", "NONE",
                stdout=asyncio.subprocess.PIPE,
            )).wait()

        # Enable and connect
        await (await asyncio.create_subprocess_exec(
            "wpa_cli", "-i", "wlan0", "enable_network", network_id,
            stdout=asyncio.subprocess.PIPE,
        )).wait()
        await (await asyncio.create_subprocess_exec(
            "wpa_cli", "-i", "wlan0", "save_config",
            stdout=asyncio.subprocess.PIPE,
        )).wait()

        # Wait for connection
        for _ in range(10):
            await asyncio.sleep(1)
            status = await self._wpa_status()
            if status.connected:
                logger.info("Connected to WiFi: %s", ssid)
                return True

        logger.error("WiFi connection to '%s' timed out", ssid)
        return False

    async def _wpa_status(self) -> WifiStatus:
        proc = await asyncio.create_subprocess_exec(
            "wpa_cli", "-i", "wlan0", "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        status = WifiStatus()
        for line in stdout.decode().strip().splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key == "ssid":
                status.ssid = value
            elif key == "ip_address":
                status.ip_address = value
            elif key == "wpa_state" and value == "COMPLETED":
                status.connected = True

        return status

    # --- Mock ---

    @staticmethod
    def _mock_scan() -> list[WifiNetwork]:
        return [
            WifiNetwork(ssid="HomeNetwork", signal=85, security="wpa2"),
            WifiNetwork(ssid="Neighbor-5G", signal=45, security="wpa2"),
            WifiNetwork(ssid="FreeWifi", signal=30, security="open"),
        ]
