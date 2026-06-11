"""Smoke tests for system/install.sh.

We can't run the script (root + apt + reboot), but we can check that
the H5 hardening stays in place: idempotency marker, single-line
cmdline.txt patch, apt retry wrapper, and overridable HifiBerry overlay.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parent.parent / "system" / "install.sh"
UNINSTALL_SH = Path(__file__).resolve().parent.parent / "system" / "uninstall.sh"
PROBE_SH = Path(__file__).resolve().parent.parent / "system" / "imager-wifi-probe.sh"

BASH = shutil.which("bash")


@pytest.fixture(scope="module")
def install_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def uninstall_text() -> str:
    return UNINSTALL_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def probe_text() -> str:
    return PROBE_SH.read_text(encoding="utf-8")


def test_install_marker_short_circuits_reruns(install_text: str) -> None:
    """H5: a completed install must not run the whole script a second time."""
    assert "INSTALL_MARKER=" in install_text
    # Marker is written LAST, so a partial failure doesn't create it
    assert install_text.rindex('"$INSTALL_MARKER"') > install_text.index("apt_retry")
    # Re-run check exists and exits early
    assert 'if [ -f "$INSTALL_MARKER" ] && [ "$FORCE_REINSTALL" = false ]' in install_text


def test_force_flag_bypasses_marker(install_text: str) -> None:
    """H5: operators must have an escape hatch when they actually want to re-run."""
    assert "--force" in install_text
    assert "--reinstall" in install_text
    assert "FORCE_REINSTALL=true" in install_text


def test_apt_retry_is_used_for_network_steps(install_text: str) -> None:
    """H5: fragile first-boot WiFi must not kill the whole install on a single flake."""
    assert "apt_retry()" in install_text
    assert "apt_retry apt-get update" in install_text
    assert "apt_retry apt-get install" in install_text


def test_cmdline_patch_only_touches_line_one(install_text: str) -> None:
    """H5: cmdline.txt must stay single-line; `1 s/...` not `s/...`."""
    # Old buggy form would append to EVERY line in a multi-line file
    assert "sed -i '1 s/$/ ipv6.disable=1/'" in install_text
    assert "sed -i 's/$/ ipv6.disable=1/'" not in install_text


def test_hifiberry_overlay_is_configurable(install_text: str) -> None:
    """H5: Amp2/DAC+ boards need a different overlay than the default."""
    assert 'HIFIBERRY_OVERLAY="${HIFIBERRY_OVERLAY:-hifiberry-dac}"' in install_text
    # The written dtoverlay line uses the variable, not a hard-coded value
    assert 'echo "dtoverlay=${HIFIBERRY_OVERLAY}"' in install_text


def test_hifiberry_check_matches_any_variant(install_text: str) -> None:
    """Idempotency: re-running with a different HIFIBERRY_OVERLAY must not duplicate."""
    assert 'grep -qE "^dtoverlay=hifiberry-"' in install_text


def test_probe_scans_before_the_connectivity_poll(probe_text: str) -> None:
    """The scan must run BEFORE the is_connected poll loop (the only NM-managed
    window), so the AP decision is never delayed by it."""
    scan_idx = probe_text.index("write_scan_cache")
    poll_idx = probe_text.index("for _ in $(seq 1")
    assert scan_idx < poll_idx, "scan must precede the connectivity poll"


def test_probe_scan_has_hard_timeout(probe_text: str) -> None:
    """The scan is wrapped in `timeout` so a hung radio can never stall boot."""
    assert "SCAN_TIMEOUT=8" in probe_text
    assert 'timeout "${SCAN_TIMEOUT}"' in probe_text
    assert "nmcli -t -f SSID,SIGNAL,SECURITY device wifi list --rescan yes" in probe_text


def test_probe_emits_scan_cache_per_contract(probe_text: str) -> None:
    """Frozen wizard contract: /run/tonado/wifi-scan.json with scanned_at +
    networks[], atomic write (tempfile + mv)."""
    assert 'SCAN_FILE="${FLAG_DIR}/wifi-scan.json"' in probe_text
    assert '"scanned_at":%s,"networks":[%s]' in probe_text
    # Atomic write: mktemp + mv.
    assert "mktemp" in probe_text
    assert 'mv -f "${tmpfile}" "${SCAN_FILE}"' in probe_text


def test_probe_scan_never_aborts_the_unit(probe_text: str) -> None:
    """A scan failure must fall through to the unchanged poll, not fail the unit."""
    assert "write_scan_cache || true" in probe_text
    # The original always-exit-0 contract is preserved.
    assert probe_text.rstrip().endswith("exit 0")


def test_uninstall_clears_marker(uninstall_text: str) -> None:
    """H5: uninstalling must reset the marker so the next install runs fresh."""
    assert "/var/lib/tonado" in uninstall_text
    assert "rm -rf /var/lib/tonado" in uninstall_text


# ---------------------------------------------------------------------------
# Real parser execution (not a text grep): this drives the ACTUAL bash
# write_scan_cache + json_escape logic and asserts the emitted JSON is valid
# and round-trips. The pure-text tests above never exercised the parser, so a
# broken escaped-colon split (the BLOCKER fix) sailed through unnoticed. The
# script is plain bash; we run it through Git Bash (ships on the Windows dev
# box). Skipped if no bash is on PATH, like test_apply_audio_overlay.py.
# ---------------------------------------------------------------------------

bash_required = pytest.mark.skipif(BASH is None, reason="bash not available on PATH")


def _run_probe_scan(tmp_path: Path, nmcli_lines: list[str]) -> dict:
    """Run the probe's REAL scan/parse pipeline against fixture nmcli output.

    Mocks `nmcli` (emits the fixture lines) and `timeout` (transparent passthrough)
    on PATH, points the probe's FLAG_DIR at a temp dir, truncates the script right
    after `write_scan_cache || true` so the 30 s connectivity poll never runs, then
    parses the emitted /run/tonado/wifi-scan.json. Returns the parsed JSON dict.
    """
    work = tmp_path
    mockbin = work / "mockbin"
    mockbin.mkdir()

    # nmcli mock: ignore all args, print the fixture lines verbatim.
    nmcli = mockbin / "nmcli"
    nmcli.write_text(
        "#!/bin/bash\n"
        + "".join(f"printf '%s\\n' {_sh_squote(line)}\n" for line in nmcli_lines),
        encoding="utf-8",
        newline="\n",
    )
    nmcli.chmod(0o755)

    # timeout mock: drop the duration arg, exec the rest (so the nmcli mock runs).
    timeout = mockbin / "timeout"
    timeout.write_text(
        '#!/bin/bash\nshift\nexec "$@"\n', encoding="utf-8", newline="\n"
    )
    timeout.chmod(0o755)

    run_dir = work / "run"
    run_dir.mkdir()

    # Build a truncated copy of the real script: everything up to and including
    # `write_scan_cache || true`, with FLAG_DIR redirected to our temp dir. This
    # keeps the real json_escape/map_security/write_scan_cache verbatim.
    src = PROBE_SH.read_text(encoding="utf-8")
    marker = "write_scan_cache || true"
    assert marker in src, "probe script no longer calls write_scan_cache"
    head = src[: src.index(marker) + len(marker)] + "\n"
    flag_dir = str(run_dir).replace("\\", "/")
    head = head.replace('FLAG_DIR="/run/tonado"', f'FLAG_DIR="{flag_dir}"')

    trunc = work / "probe_trunc.sh"
    trunc.write_text(head, encoding="utf-8", newline="\n")

    env = dict(os.environ)
    env["PATH"] = str(mockbin) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        [BASH, str(trunc)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr

    scan_file = run_dir / "wifi-scan.json"
    assert scan_file.exists(), "probe did not emit wifi-scan.json"
    return json.loads(scan_file.read_text(encoding="utf-8"))


def _sh_squote(s: str) -> str:
    """Single-quote a string for safe embedding in the generated bash mock."""
    return "'" + s.replace("'", "'\\''") + "'"


@bash_required
def test_probe_parser_round_trips_escaped_colon_ssid(tmp_path: Path) -> None:
    """BLOCKER regression: an SSID containing a colon (nmcli emits it as '\\:')
    must round-trip through the real parser, and a neighbouring colon-bearing
    SSID must NOT corrupt the JSON. A text grep can never catch this — only
    running write_scan_cache + json.loads does."""
    data = _run_probe_scan(
        tmp_path,
        [
            r"MeinWLAN\:Gast:72:WPA2",  # escaped-colon SSID
            "HomeNet:88:WPA1 WPA2",  # normal neighbour
        ],
    )
    nets = {n["ssid"]: n for n in data["networks"]}

    # The escaped-colon SSID round-trips exactly, with correct signal + security.
    assert "MeinWLAN:Gast" in nets, f"escaped-colon SSID mangled; got {list(nets)}"
    assert nets["MeinWLAN:Gast"]["signal"] == 72
    assert nets["MeinWLAN:Gast"]["security"] == "wpa2"

    # The neighbour is intact (the old bug replaced its separators too).
    assert nets["HomeNet"]["signal"] == 88
    assert nets["HomeNet"]["security"] == "wpa2"

    # scanned_at is an int per the wizard contract.
    assert isinstance(data["scanned_at"], int)


@bash_required
def test_probe_parser_handles_open_and_hidden_networks(tmp_path: Path) -> None:
    """Open networks map to 'open'; hidden (empty-SSID) rows are skipped."""
    data = _run_probe_scan(
        tmp_path,
        [
            "OpenCafe:40:",  # empty SECURITY => open
            ":12:WPA2",  # hidden SSID => skipped
        ],
    )
    nets = {n["ssid"]: n for n in data["networks"]}
    assert nets["OpenCafe"]["security"] == "open"
    assert "" not in nets, "hidden (empty-SSID) network must be skipped"


@bash_required
def test_probe_json_escapes_control_chars(tmp_path: Path) -> None:
    """An exotic SSID with a control char must not emit a raw control byte that
    strict JSON parsers reject — json.loads succeeding here is the assertion."""
    data = _run_probe_scan(
        tmp_path,
        ["Wi\x07Fi\x1fX:55:WPA2"],  # BELL (0x07) + unit-separator (0x1f)
    )
    nets = {n["ssid"]: n for n in data["networks"]}
    # Round-trips through strict JSON with the control chars preserved.
    assert "Wi\x07Fi\x1fX" in nets, list(nets)
    assert nets["Wi\x07Fi\x1fX"]["security"] == "wpa2"
