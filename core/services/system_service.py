"""System management service.

Provides system info, restart/shutdown, updates, OverlayFS control,
and watchdog configuration.
"""

import asyncio
import logging
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SystemInfo:
    """System information snapshot."""

    hostname: str = ""
    pi_model: str = ""
    os_version: str = ""
    python_version: str = ""
    tonado_version: str = "0.1.0"
    uptime_seconds: float = 0
    cpu_temp: float = 0
    ram_total_mb: int = 0
    ram_used_mb: int = 0
    disk_total_gb: float = 0
    disk_used_gb: float = 0
    overlay_active: bool = False
    ip_address: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "pi_model": self.pi_model,
            "os_version": self.os_version,
            "python_version": self.python_version,
            "tonado_version": self.tonado_version,
            "uptime_seconds": self.uptime_seconds,
            "cpu_temp": self.cpu_temp,
            "ram_total_mb": self.ram_total_mb,
            "ram_used_mb": self.ram_used_mb,
            "disk_total_gb": round(self.disk_total_gb, 1),
            "disk_used_gb": round(self.disk_used_gb, 1),
            "overlay_active": self.overlay_active,
            "ip_address": self.ip_address,
        }


class SystemService:
    """System management operations."""

    def __init__(self, install_dir: Path = Path("/opt/tonado")) -> None:
        self._install_dir = install_dir
        self._is_pi = Path("/proc/cpuinfo").exists()

    async def get_info(self) -> SystemInfo:
        """Gather system information."""
        info = SystemInfo(
            hostname=platform.node(),
            os_version=platform.platform(),
            python_version=platform.python_version(),
        )

        if self._is_pi:
            info.pi_model = self._read_file("/proc/device-tree/model") or "unknown"
            info.uptime_seconds = self._get_uptime()
            info.cpu_temp = self._get_cpu_temp()
            info.ip_address = await self._get_ip()

            # RAM info
            meminfo = self._read_file("/proc/meminfo") or ""
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    info.ram_total_mb = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    info.ram_used_mb = info.ram_total_mb - int(line.split()[1]) // 1024

            # Disk usage
            try:
                usage = shutil.disk_usage("/")
                info.disk_total_gb = usage.total / (1024**3)
                info.disk_used_gb = usage.used / (1024**3)
            except OSError:
                pass

            # OverlayFS check
            mounts = self._read_file("/proc/mounts") or ""
            info.overlay_active = "overlay / " in mounts

        return info

    async def restart(self) -> None:
        """Restart Tonado service."""
        if self._is_pi:
            logger.info("Restarting Tonado service...")
            await self._run("systemctl", "restart", "tonado.service")
        else:
            logger.info("Restart requested (no-op on non-Pi)")

    async def shutdown(self) -> None:
        """Shutdown the system."""
        if self._is_pi:
            logger.info("System shutdown initiated...")
            await self._run("shutdown", "-h", "now")
        else:
            logger.info("Shutdown requested (no-op on non-Pi)")

    async def reboot(self) -> None:
        """Reboot the system."""
        if self._is_pi:
            logger.info("System reboot initiated...")
            await self._run("reboot")
        else:
            logger.info("Reboot requested (no-op on non-Pi)")

    async def check_update(self) -> dict[str, Any]:
        """Check if an update is available via git."""
        if not (self._install_dir / ".git").exists():
            return {"available": False, "error": "Kein Git-Repository"}

        try:
            await self._run("git", "-C", str(self._install_dir), "fetch", "--quiet")
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(self._install_dir), "log", "HEAD..origin/main", "--oneline",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            commits = stdout.decode().strip().splitlines()

            return {
                "available": len(commits) > 0,
                "commits": len(commits),
                "changes": commits[:10],
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def apply_update(self) -> dict[str, Any]:
        """Pull latest changes and restart."""
        if not (self._install_dir / ".git").exists():
            return {"success": False, "error": "Kein Git-Repository"}

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(self._install_dir), "pull", "--ff-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return {"success": False, "error": stderr.decode().strip()}

            # Reinstall dependencies
            venv_pip = self._install_dir / ".venv" / "bin" / "pip"
            if venv_pip.exists():
                await self._run(str(venv_pip), "install", "-e", ".[pi]", "--quiet")

            # Restart service
            await self.restart()

            return {"success": True, "output": stdout.decode().strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def enable_overlay(self) -> bool:
        """Enable read-only root filesystem with OverlayFS."""
        if not self._is_pi:
            return False
        # Uses raspi-config to enable overlay
        result = await self._run("raspi-config", "nonint", "enable_overlayfs")
        return result == 0

    async def disable_overlay(self) -> bool:
        """Disable OverlayFS (make root writable again)."""
        if not self._is_pi:
            return False
        result = await self._run("raspi-config", "nonint", "disable_overlayfs")
        return result == 0

    async def setup_watchdog(self) -> None:
        """Configure hardware watchdog for auto-recovery."""
        if not self._is_pi:
            return

        # Enable hardware watchdog in boot config
        boot_config = Path("/boot/config.txt")
        if boot_config.exists():
            content = boot_config.read_text()
            if "dtparam=watchdog=on" not in content:
                with open(boot_config, "a") as f:
                    f.write("\n# Tonado watchdog\ndtparam=watchdog=on\n")

        # Configure systemd watchdog for tonado.service
        logger.info("Watchdog configured")

    # --- Helpers ---

    @staticmethod
    def _read_file(path: str) -> str | None:
        try:
            return Path(path).read_text().strip()
        except (OSError, UnicodeDecodeError):
            return None

    @staticmethod
    def _get_uptime() -> float:
        try:
            content = Path("/proc/uptime").read_text()
            return float(content.split()[0])
        except (OSError, ValueError):
            return 0

    @staticmethod
    def _get_cpu_temp() -> float:
        try:
            content = Path("/sys/class/thermal/thermal_zone0/temp").read_text()
            return int(content.strip()) / 1000.0
        except (OSError, ValueError):
            return 0

    @staticmethod
    async def _get_ip() -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "hostname", "-I",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip().split()[0] if stdout else ""
        except Exception:
            return ""

    @staticmethod
    async def _run(*cmd: str) -> int:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode or 0
        except FileNotFoundError:
            return 1
