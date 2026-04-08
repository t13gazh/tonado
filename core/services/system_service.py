"""System management service.

Provides system info, restart/shutdown, updates, OverlayFS control,
and watchdog configuration.
"""

import asyncio
import logging
import platform
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.services.base import BaseService
from core.utils.subprocess import async_run

logger = logging.getLogger(__name__)


def _read_version() -> str:
    """Read version from pyproject.toml (avoids import dependency)."""
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    try:
        for line in pyproject.read_text().splitlines():
            if line.strip().startswith("version"):
                return line.split('"')[1]
    except (OSError, IndexError):
        pass
    return "0.0.0"


VERSION = _read_version()


@dataclass
class SystemInfo:
    """System information snapshot."""

    hostname: str = ""
    pi_model: str = ""
    os_version: str = ""
    python_version: str = ""
    tonado_version: str = VERSION
    uptime_seconds: float = 0
    cpu_temp: float = 0
    ram_total_mb: int = 0
    ram_used_mb: int = 0
    disk_total_gb: float = 0
    disk_used_gb: float = 0
    overlay_active: bool = False
    ip_address: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["disk_total_gb"] = round(self.disk_total_gb, 1)
        d["disk_used_gb"] = round(self.disk_used_gb, 1)
        return d


class SystemService(BaseService):
    """System management operations."""

    def __init__(self, install_dir: Path = Path("/opt/tonado")) -> None:
        super().__init__()
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
        """Restart Tonado service (fire-and-forget so HTTP response is sent first)."""
        if self._is_pi:
            logger.info("Restarting Tonado service...")
            self._fire_and_forget("sudo", "systemctl", "restart", "tonado.service")
        else:
            logger.info("Restart requested (no-op on non-Pi)")

    async def shutdown(self) -> None:
        """Shutdown the system (fire-and-forget so HTTP response is sent first)."""
        if self._is_pi:
            logger.info("System shutdown initiated...")
            self._fire_and_forget("sudo", "shutdown", "-h", "now")
        else:
            logger.info("Shutdown requested (no-op on non-Pi)")

    async def reboot(self) -> None:
        """Reboot the system (fire-and-forget so HTTP response is sent first)."""
        if self._is_pi:
            logger.info("System reboot initiated...")
            self._fire_and_forget("sudo", "reboot")
        else:
            logger.info("Reboot requested (no-op on non-Pi)")

    @staticmethod
    def get_version() -> str:
        return VERSION

    async def _git(self, *args: str) -> tuple[int, str, str]:
        """Run a git command in the install directory."""
        rc, stdout, stderr = await async_run(
            ["git", "-C", str(self._install_dir), *args], timeout=60
        )
        return rc, stdout.strip(), stderr.strip()

    async def check_update(self) -> dict[str, Any]:
        """Check if an update is available via git."""
        if not (self._install_dir / ".git").exists():
            return {"available": False, "error": "Kein Git-Repository"}

        try:
            await self._git("fetch", "--quiet")

            # Get current and remote version from pyproject.toml
            _, remote_content, _ = await self._git(
                "show", "origin/main:pyproject.toml",
            )
            remote_version = VERSION
            for line in remote_content.splitlines():
                if line.strip().startswith("version"):
                    try:
                        remote_version = line.split('"')[1]
                    except IndexError:
                        pass
                    break

            # Get commit count
            _, commit_log, _ = await self._git(
                "log", "HEAD..origin/main", "--oneline",
            )
            commits = commit_log.splitlines() if commit_log else []

            # Get user-friendly changelog from remote
            changelog = ""
            if commits:
                changelog = await self._extract_remote_changelog(remote_version)

            return {
                "available": len(commits) > 0,
                "commits": len(commits),
                "changelog": changelog,
                "current_version": VERSION,
                "remote_version": remote_version,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _extract_remote_changelog(self, remote_version: str) -> str:
        """Extract the changelog section for a specific version from remote."""
        try:
            rc, content, _ = await self._git(
                "show", "origin/main:CHANGELOG.md",
            )
            if rc != 0 or not content:
                return ""

            # Find the section for this version: ## [x.y.z...] — date
            lines = content.splitlines()
            section: list[str] = []
            capturing = False

            for line in lines:
                if line.startswith("## ["):
                    if capturing:
                        break  # Next version section — stop
                    if remote_version in line:
                        capturing = True
                        continue  # Skip the header itself
                elif capturing:
                    # Skip compare links at the bottom
                    if line.startswith("[") and "]: http" in line:
                        break
                    section.append(line)

            # Trim leading/trailing blank lines
            text = "\n".join(section).strip()
            return text
        except Exception:
            return ""

    async def apply_update(self) -> dict[str, Any]:
        """Pull latest changes with rollback on failure, then restart."""
        if not (self._install_dir / ".git").exists():
            return {"success": False, "error": "Kein Git-Repository"}

        # Save current commit for rollback
        rc, current_hash, _ = await self._git("rev-parse", "HEAD")
        if rc != 0:
            return {"success": False, "error": "Git-Status unbekannt"}

        try:
            # Pull latest (fast-forward only, safe)
            rc, stdout, stderr = await self._git("pull", "--ff-only")
            if rc != 0:
                return {"success": False, "error": stderr or "git pull fehlgeschlagen"}

            # Reinstall Python dependencies if pyproject.toml changed
            rc_diff, diff_out, _ = await self._git(
                "diff", f"{current_hash}..HEAD", "--name-only",
            )
            changed_files = diff_out.splitlines() if diff_out else []

            if "pyproject.toml" in changed_files:
                logger.info("pyproject.toml changed — reinstalling dependencies")
                venv_pip = self._install_dir / ".venv" / "bin" / "pip"
                if venv_pip.exists():
                    pip_rc = await self._run(
                        str(venv_pip), "install", "-e", ".[pi]", "--quiet",
                    )
                    if pip_rc != 0:
                        logger.error("pip install failed — rolling back")
                        await self._git("reset", "--hard", current_hash)
                        return {
                            "success": False,
                            "error": "Abhängigkeiten konnten nicht installiert werden. Rollback durchgeführt.",
                        }

            # Get new version
            new_version = _read_version()
            logger.info("Update applied: %s → %s", VERSION, new_version)

            # Restart service
            await self.restart()

            return {
                "success": True,
                "output": stdout,
                "old_version": VERSION,
                "new_version": new_version,
                "files_changed": len(changed_files),
            }
        except Exception as e:
            # Rollback on any unexpected error
            logger.error("Update failed: %s — rolling back", e)
            await self._git("reset", "--hard", current_hash)
            return {
                "success": False,
                "error": f"Update fehlgeschlagen: {e}. Rollback durchgeführt.",
            }

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
    def _fire_and_forget(*cmd: str, delay: float = 1.0) -> None:
        """Schedule a system command after a short delay.

        The delay gives FastAPI enough time to send the HTTP response
        before the process is killed (restart) or the system goes down
        (reboot/shutdown).  The subprocess is fully detached so it
        survives this Python process being terminated.
        """
        import subprocess  # noqa: delayed import — only used for power commands

        async def _run_after_delay() -> None:
            await asyncio.sleep(delay)
            try:
                subprocess.Popen(
                    list(cmd),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception as exc:
                logger.error("Fire-and-forget command failed: %s — %s", cmd, exc)

        asyncio.get_running_loop().create_task(_run_after_delay())

    @staticmethod
    def _read_file(path: str) -> str | None:
        try:
            return Path(path).read_text().strip("\x00").strip()
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
        rc, stdout, _ = await async_run(["hostname", "-I"], timeout=5)
        if rc == 0 and stdout.strip():
            return stdout.strip().split()[0]
        return ""

    @staticmethod
    async def _run(*cmd: str) -> int:
        rc, _, _ = await async_run(list(cmd))
        return rc
