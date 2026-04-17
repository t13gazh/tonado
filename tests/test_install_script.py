"""Smoke tests for system/install.sh.

We can't run the script (root + apt + reboot), but we can check that
the H5 hardening stays in place: idempotency marker, single-line
cmdline.txt patch, apt retry wrapper, and overridable HifiBerry overlay.
"""

from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parent.parent / "system" / "install.sh"
UNINSTALL_SH = Path(__file__).resolve().parent.parent / "system" / "uninstall.sh"


@pytest.fixture(scope="module")
def install_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def uninstall_text() -> str:
    return UNINSTALL_SH.read_text(encoding="utf-8")


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


def test_uninstall_clears_marker(uninstall_text: str) -> None:
    """H5: uninstalling must reset the marker so the next install runs fresh."""
    assert "/var/lib/tonado" in uninstall_text
    assert "rm -rf /var/lib/tonado" in uninstall_text
