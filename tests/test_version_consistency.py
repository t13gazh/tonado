"""Guards against version drift across the repo.

`pyproject.toml` is the single source of truth (read at runtime by
`system_service._read_version`). Every other place that hardcodes the
version — `web/package.json`, the README badge, the README status line —
must match it. This test exists because the version was bumped at release
time but the README was forgotten more than once.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "no version field in pyproject.toml"
    return match.group(1)


def test_package_json_matches_pyproject() -> None:
    version = _pyproject_version()
    pkg = json.loads((REPO_ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == version, (
        f"web/package.json version {pkg['version']!r} != pyproject {version!r} "
        "— bump both on release"
    )


def test_readme_badge_matches_pyproject() -> None:
    version = _pyproject_version()
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # shields.io escapes a literal hyphen as a double hyphen.
    badge = f"version-{version.replace('-', '--')}-blue"
    assert badge in readme, (
        f"README version badge does not show {version!r} "
        f"(expected fragment {badge!r}) — update it on release"
    )


def test_readme_status_line_matches_pyproject() -> None:
    version = _pyproject_version()
    base = version.split("-", 1)[0]  # "0.3.1-beta" -> "0.3.1"
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    status = readme.split("## Status", 1)
    assert len(status) == 2, "README has no '## Status' section"
    assert f"v{base}" in status[1], (
        f"README status section does not mention v{base} — update it on release"
    )
