"""Contract + idempotency tests for system/apply-audio-overlay.sh.

The helper is invoked by the setup wizard (via sudo, FIXED argv) to flip the
I2S DAC overlay in config.txt. These tests assert:
  * the argv contract (only i2s/analog accepted, anything else exits non-zero),
  * the config.txt edits in both directions, and
  * idempotency (running twice yields no further change).

The script is plain bash; we drive it through Git Bash, which ships on the
Windows dev box. The test is skipped if no bash is on PATH (e.g. a bare CI
runner without it) so the suite never hard-fails on platform.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "system" / "apply-audio-overlay.sh"

BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available on PATH")


# A representative config.txt with onboard audio enabled and no overlay yet.
BASE_CONFIG = """\
# For more options and information see
[all]
dtparam=audio=on
dtparam=spi=on
dtparam=i2c_arm=on
"""


def _run(boot_config: Path, mode: str) -> subprocess.CompletedProcess[str]:
    """Run apply-audio-overlay.sh with an overridden config.txt location.

    The script resolves /boot/firmware/config.txt or /boot/config.txt; we point
    BOOT_CONFIG at the fixture by pre-seeding the candidate path. Rather than
    fake /boot, we exploit that the script picks the firmware path first only if
    it exists — so we run a tiny wrapper that overrides the resolved path via a
    sed of the script is overkill. Instead we copy the script and patch the two
    resolution lines to use our fixture. Keeps the real script untouched.
    """
    patched = boot_config.parent / "apply-audio-overlay.sh"
    src = SCRIPT.read_text(encoding="utf-8")
    # Replace the hard-coded resolution with our fixture path. Both candidate
    # lines are replaced so the `-f` guard still passes against the fixture.
    cfg = str(boot_config).replace("\\", "/")
    src = src.replace(
        'BOOT_CONFIG="/boot/firmware/config.txt"\n'
        '[ ! -f "$BOOT_CONFIG" ] && BOOT_CONFIG="/boot/config.txt"',
        f'BOOT_CONFIG="{cfg}"',
    )
    patched.write_text(src, encoding="utf-8", newline="\n")
    return subprocess.run(
        [BASH, str(patched), mode],
        capture_output=True,
        text=True,
    )


def test_rejects_missing_arg(tmp_path: Path) -> None:
    cfg = tmp_path / "config.txt"
    cfg.write_text(BASE_CONFIG, encoding="utf-8", newline="\n")
    patched = tmp_path / "apply-audio-overlay.sh"
    src = SCRIPT.read_text(encoding="utf-8").replace(
        'BOOT_CONFIG="/boot/firmware/config.txt"\n'
        '[ ! -f "$BOOT_CONFIG" ] && BOOT_CONFIG="/boot/config.txt"',
        f'BOOT_CONFIG="{str(cfg).replace(chr(92), "/")}"',
    )
    patched.write_text(src, encoding="utf-8", newline="\n")
    result = subprocess.run([BASH, str(patched)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()


def test_rejects_unknown_arg(tmp_path: Path) -> None:
    cfg = tmp_path / "config.txt"
    cfg.write_text(BASE_CONFIG, encoding="utf-8", newline="\n")
    result = _run(cfg, "bluetooth")
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()


def test_fails_loud_when_config_missing(tmp_path: Path) -> None:
    """No config.txt anywhere => non-zero exit + stderr, no silent success."""
    missing = tmp_path / "config.txt"  # deliberately not created
    result = _run(missing, "i2s")
    assert result.returncode != 0
    assert "config.txt not found" in result.stderr.lower()


def test_i2s_enables_overlay_and_mutes_onboard(tmp_path: Path) -> None:
    cfg = tmp_path / "config.txt"
    cfg.write_text(BASE_CONFIG, encoding="utf-8", newline="\n")
    result = _run(cfg, "i2s")
    assert result.returncode == 0, result.stderr
    text = cfg.read_text(encoding="utf-8")
    # Onboard audio commented out, DAC overlay + LED gpio appended.
    assert "#dtparam=audio=on" in text
    assert "\ndtparam=audio=on" not in "\n" + text  # no active onboard line left
    assert "dtoverlay=hifiberry-dac" in text
    assert "gpio=25=op,dh" in text


def test_i2s_is_idempotent(tmp_path: Path) -> None:
    cfg = tmp_path / "config.txt"
    cfg.write_text(BASE_CONFIG, encoding="utf-8", newline="\n")
    _run(cfg, "i2s")
    after_first = cfg.read_text(encoding="utf-8")
    result = _run(cfg, "i2s")
    assert result.returncode == 0, result.stderr
    after_second = cfg.read_text(encoding="utf-8")
    assert after_first == after_second, "second i2s run must not change the file"
    # No duplicate overlay line.
    assert after_second.count("dtoverlay=hifiberry-dac") == 1


def test_analog_reverses_i2s(tmp_path: Path) -> None:
    cfg = tmp_path / "config.txt"
    cfg.write_text(BASE_CONFIG, encoding="utf-8", newline="\n")
    _run(cfg, "i2s")
    result = _run(cfg, "analog")
    assert result.returncode == 0, result.stderr
    text = cfg.read_text(encoding="utf-8")
    # Onboard audio re-enabled (active, uncommented), overlay commented out.
    lines = text.splitlines()
    assert "dtparam=audio=on" in lines  # active line present again
    assert "#dtoverlay=hifiberry-dac" in text
    # No ACTIVE hifiberry overlay line remains.
    assert not any(line.startswith("dtoverlay=hifiberry-") for line in lines)


def test_analog_is_idempotent(tmp_path: Path) -> None:
    cfg = tmp_path / "config.txt"
    cfg.write_text(BASE_CONFIG, encoding="utf-8", newline="\n")
    _run(cfg, "i2s")
    _run(cfg, "analog")
    after_first = cfg.read_text(encoding="utf-8")
    result = _run(cfg, "analog")
    assert result.returncode == 0, result.stderr
    after_second = cfg.read_text(encoding="utf-8")
    assert after_first == after_second, "second analog run must not change the file"


def test_analog_on_clean_onboard_is_noop(tmp_path: Path) -> None:
    """analog on a config that already has onboard audio active => no change."""
    cfg = tmp_path / "config.txt"
    cfg.write_text(BASE_CONFIG, encoding="utf-8", newline="\n")
    before = cfg.read_text(encoding="utf-8")
    result = _run(cfg, "analog")
    assert result.returncode == 0, result.stderr
    assert cfg.read_text(encoding="utf-8") == before
