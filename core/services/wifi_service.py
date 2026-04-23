"""WiFi management service.

Manages WiFi connections via NetworkManager (nmcli) on the Pi.
Falls back to wpa_supplicant if NetworkManager is unavailable.
"""

import asyncio
import logging
import os
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from core.services.base import BaseService

logger = logging.getLogger(__name__)


# --- Confirm-complete token registry ---
#
# /api/setup/test-wifi (and the legacy /api/setup/wifi/connect probe path)
# return a one-shot token after a successful home-WiFi probe. The client
# must echo that token back to /api/setup/confirm-complete within the TTL
# below — otherwise an attacker who could reach /confirm-complete without
# ever having proven they own a working probe could trigger AP teardown.
#
# Kept in-process: the wizard runs in a single boot window, and a token
# that survives a restart would be more risk (reuse across reboots) than
# value. The registry is at module scope so both wifi_service and the
# setup router can access it without an extra DI wire.
_CONFIRM_TOKEN_TTL_SECONDS = 600  # 10 minutes
_confirm_tokens: dict[str, float] = {}


def _issue_confirm_token() -> str:
    """Create a fresh confirm-complete token, pruning any expired ones."""
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    # Drop expired entries so the dict doesn't grow unboundedly across
    # probe attempts.
    for existing in list(_confirm_tokens):
        if _confirm_tokens[existing] < now:
            _confirm_tokens.pop(existing, None)
    _confirm_tokens[token] = now + _CONFIRM_TOKEN_TTL_SECONDS
    return token


def consume_confirm_token(token: str | None) -> bool:
    """Validate and single-use-consume a confirm-complete token.

    Returns True iff the token was present and unexpired. Always removes
    it from the registry so replays fail even within the TTL window.
    """
    if not token:
        return False
    expiry = _confirm_tokens.pop(token, None)
    if expiry is None:
        return False
    if expiry < time.monotonic():
        return False
    return True


def clear_confirm_tokens() -> None:
    """Drop all outstanding tokens (used from finalize + test helpers)."""
    _confirm_tokens.clear()


@dataclass
class WifiNetwork:
    """A detected WiFi network."""

    ssid: str
    signal: int  # 0-100
    security: str  # "open", "wpa", "wpa2", "wep"
    connected: bool = False


@dataclass
class WifiStatus:
    """Current WiFi connection status."""

    connected: bool = False
    ssid: str = ""
    ip_address: str = ""
    signal: int = 0


class WifiService(BaseService):
    """Manages WiFi connections on the Raspberry Pi."""

    # After this many consecutive probe failures, lock the wizard out and
    # force a box-restart. An attacker on the setup AP would otherwise have
    # unlimited PSK guesses against a neighbouring WiFi via /test-wifi.
    PROBE_FAIL_LOCKOUT = 10

    def __init__(self) -> None:
        super().__init__()
        self._use_nmcli = shutil.which("nmcli") is not None
        self._mock = not self._use_nmcli and shutil.which("wpa_cli") is None

        # F1: serialize finalize + guard probe attempts against a brute-force.
        # Lock covers the whole finalize path so a racing confirm-complete
        # and a late test-wifi can't interleave and leave a half-torn AP.
        self._finalize_lock = asyncio.Lock()
        self._probe_fail_count = 0

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
        """Get current WiFi connection status.

        Wrapped in a hard 10s timeout: on Pi Zero W, `nmcli` can hang for
        30s+ when the driver is misbehaving, which would otherwise block
        the ConnectivityMonitor's poll loop and stall fallback decisions.
        """
        if self._mock:
            return WifiStatus()

        try:
            if self._use_nmcli:
                return await asyncio.wait_for(self._nmcli_status(), timeout=10.0)
            return await asyncio.wait_for(self._wpa_status(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("WiFi status query timed out — treating as unknown")
            return WifiStatus()

    @staticmethod
    async def _read_subprocess(proc: asyncio.subprocess.Process) -> bytes:
        """Run `proc.communicate()` and ensure the process is reaped even
        if the caller is cancelled — otherwise a hung nmcli becomes a zombie
        that accumulates under the 10s timeout in `status()`.
        """
        try:
            stdout, _ = await proc.communicate()
            return stdout
        except asyncio.CancelledError:
            if proc.returncode is None:
                try:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
                except ProcessLookupError:
                    pass
            raise

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
        # Wrapped so a wait_for-cancel in status() reaps the subprocess
        # instead of leaving an nmcli zombie.
        stdout = await self._read_subprocess(proc)

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
                sig_out = await self._read_subprocess(sig_proc)
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
        stdout = await self._read_subprocess(proc)

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

    # --- Dual-WiFi probe and setup-AP teardown ---

    # Nomenclature:
    #   PROBE_CONNECTION_NAME — the nmcli connection profile we create
    #   during /api/setup/test-wifi. We deliberately use a fixed name so
    #   a leftover from a previous failed attempt can be cleaned up on
    #   the next try.
    PROBE_CONNECTION_NAME = "tonado-home-probe"

    SETUP_COMPLETE_MARKER = Path("/opt/tonado/config/.setup-complete")
    NM_UNMANAGED_CONF = Path(
        "/etc/NetworkManager/conf.d/99-tonado-wlan0-unmanaged.conf"
    )

    async def probe_home_wifi(
        self,
        ssid: str,
        password: str,
        timeout: int = 20,
    ) -> dict:
        """Try to connect to the home WiFi without disrupting the setup AP.

        This is the critical piece of the dual-WiFi transition during the
        setup wizard. The Pi must remain reachable via the setup AP while
        we probe the home WiFi, otherwise a user who fat-fingered their
        password would be kicked out of the wizard with no way back in.

        IMPORTANT — DO NOT SIMPLIFY:
        The implementation below deliberately creates a probe connection
        with `autoconnect no` and brings it up explicitly. On failure it
        deletes the connection profile again. The setup AP (hostapd +
        dnsmasq on wlan0) keeps running regardless of the outcome. If
        somebody refactors this to call `nmcli device wifi connect`, the
        AP will be torn down the moment nmcli tries to activate wlan0 in
        station mode, and a wrong-password user loses all access to the
        box. That path is the only way the user can correct the input —
        do not take it away.

        Returns:
            dict with keys:
              - ok (bool): whether the probe connected successfully
              - error (str | None): German user-facing error message on
                failure, None on success
              - ip (str | None): acquired IPv4 address on success, else None
              - token (str | None): one-shot confirm-complete token on
                success, else None. Must be passed back to
                /api/setup/confirm-complete within ~10 minutes.
              - locked (bool, optional): True iff the probe is locked out
                after too many consecutive failures.
        """
        # F1: too many wrong-password attempts in a row → force a box
        # restart so a neighbour on the setup AP can't brute-force a home
        # PSK. Counter resets on success and on finalize.
        if self._probe_fail_count >= self.PROBE_FAIL_LOCKOUT:
            return {
                "ok": False,
                "error": (
                    "Zu viele Fehlversuche. Bitte die Box neu starten."
                ),
                "ip": None,
                "token": None,
                "locked": True,
            }

        if self._mock:
            logger.info("Mock: probing home WiFi '%s'", ssid)
            self._probe_fail_count = 0
            return {
                "ok": True,
                "error": None,
                "ip": "192.168.1.42",
                "token": _issue_confirm_token(),
            }

        if not self._use_nmcli:
            # The dual-WiFi transition hinges on NetworkManager's ability
            # to hold multiple connection profiles simultaneously. The
            # wpa_supplicant fallback cannot do this; fail fast with a
            # clear German message so the UI can explain the situation.
            return {
                "ok": False,
                "error": "NetworkManager ist nicht verfügbar, WLAN-Test nicht möglich.",
                "ip": None,
                "token": None,
            }

        # Clean up any leftover probe connection from a previous attempt.
        # Ignore errors — the connection might simply not exist. Makes
        # repeated probes idempotent without requiring a cancel call.
        await self._nmcli_delete_connection(self.PROBE_CONNECTION_NAME)

        # Create a new connection profile. `autoconnect no` means NM will
        # not try to bring this up on its own later; we decide when.
        add_cmd = [
            "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", self.PROBE_CONNECTION_NAME,
            "ifname", "wlan0",
            "ssid", ssid,
            "connection.autoconnect", "no",
        ]
        if password:
            add_cmd += [
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
            ]

        add_proc = await asyncio.create_subprocess_exec(
            *add_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, add_err = await add_proc.communicate()
        if add_proc.returncode != 0:
            logger.error(
                "Failed to create probe connection for '%s': %s",
                ssid, add_err.decode().strip(),
            )
            # Nothing to clean up — the add failed. Count as a fail so
            # brute-force attempts can't loop over profile-add errors.
            self._probe_fail_count += 1
            return {
                "ok": False,
                "error": "WLAN-Profil konnte nicht angelegt werden.",
                "ip": None,
                "token": None,
            }

        # Try to bring it up. `--wait` gives nmcli a hard timeout so a
        # misbehaving driver cannot hang us forever; we additionally wrap
        # the whole thing in asyncio.wait_for so our caller has a
        # predictable ceiling.
        up_cmd = [
            "nmcli", "--wait", str(timeout),
            "connection", "up", self.PROBE_CONNECTION_NAME,
        ]
        up_proc = await asyncio.create_subprocess_exec(
            *up_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            _, up_err = await asyncio.wait_for(
                up_proc.communicate(),
                timeout=timeout + 5,
            )
            returncode = up_proc.returncode
            err_text = up_err.decode().strip()
        except asyncio.TimeoutError:
            # Reap the subprocess so we don't leak it.
            try:
                up_proc.kill()
                await up_proc.wait()
            except ProcessLookupError:
                pass
            returncode = -1
            err_text = "timeout"

        if returncode != 0:
            logger.warning(
                "Probe connection to '%s' failed (rc=%s): %s",
                ssid, returncode, err_text,
            )
            # Clean up the profile — we do NOT want a half-finished
            # connection lingering. Setup AP continues running because
            # we never touched it here.
            await self._nmcli_delete_connection(self.PROBE_CONNECTION_NAME)

            self._probe_fail_count += 1
            user_error = self._translate_nmcli_error(err_text)
            return {
                "ok": False,
                "error": user_error,
                "ip": None,
                "token": None,
            }

        # Connection is up. Read back the assigned IP.
        ip = await self._read_probe_ip()
        logger.info(
            "Probe connection to '%s' established, ip=%s", ssid, ip or "<none>",
        )
        # First success resets the failure counter so subsequent attempts
        # (e.g. to try a different SSID) don't inherit a near-lockout.
        self._probe_fail_count = 0
        return {
            "ok": True,
            "error": None,
            "ip": ip,
            "token": _issue_confirm_token(),
        }

    async def finalize_setup_ap_teardown(self) -> None:
        """Tear down the setup AP after the wizard has fully completed.

        Called from /api/setup/confirm-complete once the client has
        confirmed it can reach the box over the home WiFi. Order matters:

          1. Write the `.setup-complete` marker so a subsequent reboot
             will not re-enable the AP even if the following steps are
             interrupted. Written via tempfile+rename so a mid-write
             power loss can't leave a zero-byte marker that downstream
             code would still consider "setup done".
          2. Stop and disable the systemd AP unit (via sudo).
          3. Drop the NetworkManager "unmanaged wlan0" override so NM
             takes full control of the interface again — otherwise the
             home-WiFi connection we're relying on would be suspended the
             next time the AP would have claimed wlan0.

        Raises:
            RuntimeError: if any of the step-2/3 commands failed on a
                real (non-mock) Pi. Caller is expected to translate this
                into an HTTP 500 so the client knows the teardown did
                not complete and the AP may still be up.
        """
        # Serialize — an in-flight /confirm-complete must not race with
        # a concurrent one. The lock also covers the post-failure
        # confirm-token clear.
        async with self._finalize_lock:
            if self.SETUP_COMPLETE_MARKER.exists():
                # Idempotent: a double-click on the wizard's "fertig"
                # button should not re-run teardown. Exit cleanly.
                logger.info("Setup already finalized, skipping teardown")
                return

            # 1. Marker first — atomic write so a torn marker can't pass
            #    `SETUP_COMPLETE_MARKER.exists()` with zero bytes later.
            self.SETUP_COMPLETE_MARKER.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self.SETUP_COMPLETE_MARKER.parent),
                prefix=".setup-complete.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w") as handle:
                    handle.write("ok")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, self.SETUP_COMPLETE_MARKER)
            except Exception:
                # Best-effort cleanup of the temp file if replace failed.
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise

            # Drop any outstanding confirm tokens — they've served their
            # purpose and the wizard is now over.
            clear_confirm_tokens()

            if self._mock:
                logger.info("Mock: finalized setup AP teardown")
                return

            # 2. Stop and disable the AP unit via sudoers. We shell out
            #    with explicit sudo so the exact argv matches the
            #    sudoers.d/tonado grants — any drift there results in a
            #    password prompt which would hang forever.
            failures: list[tuple[str, int]] = []
            for cmd in (
                ["sudo", "-n", "systemctl", "stop", "tonado-ap.service"],
                ["sudo", "-n", "systemctl", "disable", "tonado-ap.service"],
            ):
                rc = await self._run_silent(cmd)
                if rc != 0:
                    failures.append((" ".join(cmd), rc))

            # 3. Remove the NM unmanaged drop-in so wlan0 is fully under
            #    NM control again. The file is root-owned, so use sudo.
            rm_cmd = ["sudo", "-n", "rm", str(self.NM_UNMANAGED_CONF)]
            if self.NM_UNMANAGED_CONF.exists():
                rc = await self._run_silent(rm_cmd)
                if rc != 0:
                    failures.append((" ".join(rm_cmd), rc))

            # Ask NM to reload so the dropped conf file takes effect
            # without a reboot. Best-effort but still reported.
            reload_cmd = ["sudo", "-n", "nmcli", "general", "reload"]
            rc = await self._run_silent(reload_cmd)
            if rc != 0:
                failures.append((" ".join(reload_cmd), rc))

            if failures:
                # Leave the marker in place — a reboot will still bypass
                # the AP thanks to its ConditionPathExists — but tell the
                # caller so they can surface the situation.
                detail = "; ".join(f"{c} (rc={rc})" for c, rc in failures)
                logger.error("finalize_setup_ap_teardown failures: %s", detail)
                raise RuntimeError(
                    "AP-Teardown unvollständig: " + detail
                )

    async def cancel_probe(self) -> dict:
        """Drop any lingering probe connection profile.

        The setup UI exposes this so the wizard can force-cleanup between
        retries (e.g. after a timeout the user backs out, types a
        different SSID and tries again). Safe to call when no profile is
        present — idempotent.
        """
        if self._mock or not self._use_nmcli:
            return {"ok": True}
        await self._nmcli_delete_connection(self.PROBE_CONNECTION_NAME)
        return {"ok": True}

    # --- Helpers for probe_home_wifi / finalize_setup_ap_teardown ---

    async def _nmcli_delete_connection(self, name: str) -> None:
        """Delete an nmcli connection profile, swallowing errors."""
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "connection", "delete", name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    async def _read_probe_ip(self) -> str | None:
        """Read the IPv4 address currently assigned to the probe connection."""
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "-t", "-f", "IP4.ADDRESS", "connection", "show",
            self.PROBE_CONNECTION_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        for line in stdout.decode().strip().splitlines():
            if ":" not in line:
                continue
            _, _, value = line.partition(":")
            value = value.strip()
            if value and value != "--":
                return value.split("/")[0] if "/" in value else value
        return None

    async def _run_silent(self, cmd: list[str]) -> int:
        """Run a command, discarding output. Returns the return code."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode or 0
        except FileNotFoundError:
            # Binary not installed (dev environment). Not fatal.
            return -1

    @staticmethod
    def _translate_nmcli_error(stderr: str) -> str:
        """Map an nmcli error message to a German user-facing string."""
        text = stderr.lower()
        if "secrets were required" in text or "no key available" in text:
            return "Das WLAN-Passwort ist falsch."
        if "no network with ssid" in text or "not found" in text:
            return "Das WLAN wurde nicht gefunden. SSID prüfen."
        if "timeout" in text:
            return "Zeitüberschreitung beim Verbinden. Signalstärke prüfen."
        return "Verbindung zum WLAN fehlgeschlagen."

    # --- Mock ---

    @staticmethod
    def _mock_scan() -> list[WifiNetwork]:
        return [
            WifiNetwork(ssid="HomeNetwork", signal=85, security="wpa2"),
            WifiNetwork(ssid="Neighbor-5G", signal=45, security="wpa2"),
            WifiNetwork(ssid="FreeWifi", signal=30, security="open"),
        ]
