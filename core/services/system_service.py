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
        # Serialises update/check against update/apply so `git fetch` and
        # `git pull` don't stomp on each other when two admins click at once.
        self._update_lock = asyncio.Lock()

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

        async with self._update_lock:
            return await self._check_update_unlocked()

    async def _check_update_unlocked(self) -> dict[str, Any]:
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

            # Get user-friendly release notes from remote. Primary source is
            # WAS-IST-NEU.md (parent-friendly, plain prose). CHANGELOG.md is
            # kept as dev-facing history and used as a fallback only.
            changelog = ""
            if commits:
                changelog = await self._extract_remote_section(
                    "WAS-IST-NEU.md", remote_version
                )
                if not changelog:
                    changelog = await self._extract_remote_section(
                        "CHANGELOG.md", remote_version
                    )
                if not changelog:
                    # No notes for this version in either file — show commit
                    # subjects as a last-resort hint.
                    changelog = "### Änderungen\n" + "\n".join(
                        f"- {c.split(' ', 1)[1]}" if ' ' in c else f"- {c}"
                        for c in commits
                    )

            return {
                "available": len(commits) > 0,
                "commits": len(commits),
                "changelog": changelog,
                "current_version": VERSION,
                "remote_version": remote_version,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _extract_remote_section(
        self, filename: str, remote_version: str
    ) -> str:
        """Extract the section for a specific version from a remote Markdown file.

        Used to pull either parent-friendly release notes (WAS-IST-NEU.md) or
        the developer changelog (CHANGELOG.md) depending on which source the
        caller prefers.
        """
        try:
            rc, content, _ = await self._git(
                "show", f"origin/main:{filename}",
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
        """Pull latest changes with rollback on failure, then restart.

        Serialised via _update_lock so two concurrent /update/apply clicks
        don't race on the working tree.
        """
        if not (self._install_dir / ".git").exists():
            return {"success": False, "error": "Kein Git-Repository"}

        async with self._update_lock:
            return await self._apply_update_unlocked()

    async def _apply_update_unlocked(self) -> dict[str, Any]:
        # Save current commit for rollback
        rc, current_hash, _ = await self._git("rev-parse", "HEAD")
        if rc != 0:
            return {"success": False, "error": "Git-Status unbekannt"}
        current_hash = current_hash.strip()

        logger.info(
            "Update: starting apply, install_dir=%s, current=%s",
            self._install_dir,
            current_hash,
        )

        try:
            # Discard local changes so pull succeeds even with hotfixes.
            # All local modifications are assumed to be included in the
            # incoming update (committed upstream before release).
            rc_reset, _, stderr_reset = await self._git("reset", "--hard", "HEAD")
            if rc_reset != 0:
                logger.error(
                    "Update: git reset --hard HEAD failed (rc=%d): %s",
                    rc_reset,
                    stderr_reset,
                )
                return {
                    "success": False,
                    "error": "Reset fehlgeschlagen: Arbeitsverzeichnis konnte nicht bereinigt werden.",
                }

            rc_clean, _, stderr_clean = await self._git(
                "clean", "-fd", "web/build/"
            )
            if rc_clean != 0:
                # Non-fatal: clean failing just means stale build artefacts
                # may linger. The update itself can still proceed.
                logger.warning(
                    "Update: git clean web/build/ returned rc=%d: %s",
                    rc_clean,
                    stderr_clean,
                )

            # Pull latest (fast-forward only, safe)
            rc, stdout, stderr = await self._git("pull", "--ff-only")
            if rc != 0:
                logger.error("Update: git pull failed (rc=%d): %s", rc, stderr)
                return {"success": False, "error": stderr or "git pull fehlgeschlagen"}

            # Verify the pull actually moved HEAD. When the remote has no
            # new commits, pyproject.toml may look "newer" on disk (e.g.
            # after a manual edit that reset() reverted) but HEAD is
            # unchanged — no restart, no pip, no changelog lies.
            rc_new, new_hash, _ = await self._git("rev-parse", "HEAD")
            if rc_new != 0:
                logger.error("Update: post-pull rev-parse failed (rc=%d)", rc_new)
                return {"success": False, "error": "Git-Status nach Pull unbekannt"}
            new_hash = new_hash.strip()

            if new_hash == current_hash:
                logger.info(
                    "Update: already up to date (HEAD unchanged at %s)",
                    current_hash,
                )
                return {
                    "success": True,
                    "no_changes": True,
                    "output": stdout,
                    "old_version": VERSION,
                    "new_version": VERSION,
                    "files_changed": 0,
                    "new_commit_hash": new_hash,
                }

            # Reinstall Python dependencies if pyproject.toml changed
            rc_diff, diff_out, _ = await self._git(
                "diff", f"{current_hash}..HEAD", "--name-only",
            )
            changed_files = diff_out.splitlines() if diff_out else []
            logger.info(
                "Update: pulled to %s (%d files changed)",
                new_hash,
                len(changed_files),
            )

            if "pyproject.toml" in changed_files:
                logger.info(
                    "Update: pip install starting (pyproject changed)"
                )
                venv_pip = self._install_dir / ".venv" / "bin" / "pip"
                if venv_pip.exists():
                    # pip install -e .[pi] on a Pi Zero W/3B+ can take
                    # 60-120s. Use an explicit generous timeout so the
                    # default 30s doesn't trigger a bogus rollback.
                    pip_rc, pip_out, pip_err = await async_run(
                        [
                            str(venv_pip),
                            "install",
                            "-e",
                            ".[pi]",
                            "--quiet",
                        ],
                        timeout=600,
                    )
                    if pip_rc != 0:
                        logger.error(
                            "Update: pip install failed (rc=%d): stdout=%s stderr=%s — rolling back",
                            pip_rc,
                            pip_out.strip(),
                            pip_err.strip(),
                        )
                        await self._rollback(current_hash, reinstall=True)
                        return {
                            "success": False,
                            "error": "Abhängigkeiten konnten nicht installiert werden. Rollback durchgeführt.",
                        }

            # Get new version
            new_version = _read_version()
            logger.info(
                "Update applied: %s → %s (hash=%s)",
                VERSION,
                new_version,
                new_hash,
            )

            # Restart service (fire-and-forget). The new commit hash lets
            # the client poll /api/system/info and confirm the restart
            # actually picked up the new code.
            await self.restart()

            return {
                "success": True,
                "output": stdout,
                "old_version": VERSION,
                "new_version": new_version,
                "files_changed": len(changed_files),
                "new_commit_hash": new_hash,
            }
        except Exception as e:
            # Rollback on any unexpected error. Don't reinstall deps — the
            # pip step hasn't been reached yet in this branch.
            logger.exception("Update failed — rolling back")
            await self._rollback(current_hash, reinstall=False)
            return {
                "success": False,
                "error": f"Update fehlgeschlagen: {e}. Rollback durchgeführt.",
            }

    async def _rollback(self, commit_hash: str, *, reinstall: bool) -> None:
        """Reset working tree and, when requested, reinstall deps from pyproject.

        ``reinstall`` is only set after pip has already run — otherwise the
        installed packages still match the previous pyproject and there's
        nothing to repair.
        """
        try:
            rc_reset, _, stderr_reset = await self._git(
                "reset", "--hard", commit_hash
            )
            if rc_reset != 0:
                # Rollback reset failed — the working tree is now officially
                # inconsistent (neither old nor new). Surface loudly so an
                # operator has a chance to intervene.
                logger.error(
                    "Rollback: git reset --hard %s failed (rc=%d): %s — working tree inconsistent",
                    commit_hash,
                    rc_reset,
                    stderr_reset,
                )
                return
        except Exception:
            logger.exception("git reset during rollback failed")
            return
        if not reinstall:
            return
        venv_pip = self._install_dir / ".venv" / "bin" / "pip"
        if not venv_pip.exists():
            return
        # Same rationale as the forward install: pip on a Pi Zero W can
        # take a minute or two, so override the 30s default.
        pip_rc, pip_out, pip_err = await async_run(
            [str(venv_pip), "install", "-e", ".[pi]", "--quiet"],
            timeout=600,
        )
        if pip_rc != 0:
            logger.error(
                "Rollback pip reinstall returned rc=%d: stdout=%s stderr=%s — deps may be inconsistent",
                pip_rc,
                pip_out.strip(),
                pip_err.strip(),
            )

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
        """No-op until systemd-notify integration is complete (K7).

        Previous implementation enabled dtparam=watchdog=on without a ticker,
        which would have rebooted the Pi every ~15s once /dev/watchdog was
        opened. Neutralised to prevent accidental bricking; a proper
        WatchdogSec= + sd_notify loop will land post-Beta.
        """
        logger.warning(
            "setup_watchdog() invoked but disabled until systemd-notify "
            "integration lands (K7)."
        )

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
    async def _run(*cmd: str, timeout: float = 60) -> int:
        """Run a command and return its exit code.

        The default is bumped to 60s (async_run defaults to 30s) so short
        system helpers like raspi-config have a bit more headroom. Callers
        with unclear durations (pip install, apt) MUST pass an explicit
        ``timeout`` — in practice those call sites use ``async_run``
        directly to also capture stderr.
        """
        rc, _, _ = await async_run(list(cmd), timeout=timeout)
        return rc
