"""Tests for the system/update service — K5 hardening."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.services.system_service import SystemService


@pytest.fixture
def install_dir(tmp_path: Path) -> Path:
    """Create a fake install directory that looks like a git checkout."""
    install = tmp_path / "tonado"
    (install / ".git").mkdir(parents=True)
    return install


@pytest.fixture
def svc(install_dir: Path) -> SystemService:
    service = SystemService(install_dir=install_dir)
    # Neutralise the restart() call — we don't want to reboot the test runner
    service.restart = AsyncMock(return_value=None)
    return service


def _queue(*results):
    """AsyncMock whose side_effect pops tuples from a queue."""
    mock = AsyncMock()
    mock.side_effect = list(results)
    return mock


@pytest.mark.asyncio
async def test_check_update_no_git(tmp_path: Path) -> None:
    s = SystemService(install_dir=tmp_path / "nope")
    result = await s.check_update()
    assert result["available"] is False
    assert "Git" in result["error"]


@pytest.mark.asyncio
async def test_apply_update_no_git(tmp_path: Path) -> None:
    s = SystemService(install_dir=tmp_path / "nope")
    result = await s.apply_update()
    assert result["success"] is False


@pytest.mark.asyncio
async def test_apply_update_happy_path_no_pyproject_change(svc: SystemService) -> None:
    """Happy path: git fetch/pull succeeds, pyproject untouched → no pip reinstall."""
    calls: list[tuple] = []

    async def fake_async_run(cmd, timeout=None):
        calls.append(tuple(cmd))
        # rev-parse HEAD
        if cmd[2:4] == ["rev-parse", "HEAD"]:
            return 0, "abc123\n", ""
        # reset, clean, pull, diff
        if cmd[2] == "reset":
            return 0, "", ""
        if cmd[2] == "clean":
            return 0, "", ""
        if cmd[2] == "pull":
            return 0, "Updating\n", ""
        if cmd[2] == "diff":
            # No pyproject.toml changed
            return 0, "README.md\nweb/build/app.js\n", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        result = await svc.apply_update()

    assert result["success"] is True
    svc.restart.assert_awaited_once()
    # Verify no pip install call happened
    assert not any("pip" in " ".join(c) for c in calls)


@pytest.mark.asyncio
async def test_apply_update_pip_fails_triggers_rollback_with_reinstall(
    svc: SystemService, install_dir: Path
) -> None:
    """When pyproject.toml changed and pip fails, rollback must git-reset AND reinstall deps."""
    # Pretend there's a venv pip so the rollback tries to reinstall
    venv_pip = install_dir / ".venv" / "bin" / "pip"
    venv_pip.parent.mkdir(parents=True)
    venv_pip.touch()

    reset_to_rollback = False
    pip_call_count = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal reset_to_rollback, pip_call_count
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                return 0, "oldcommit\n", ""
            if op == "reset" and cmd[-1] == "oldcommit":
                reset_to_rollback = True
                return 0, "", ""
            if op == "reset":
                return 0, "", ""
            if op == "clean":
                return 0, "", ""
            if op == "pull":
                return 0, "Fast-forward", ""
            if op == "diff":
                return 0, "pyproject.toml\n", ""  # triggers pip
        if "pip" in cmd[0]:
            pip_call_count += 1
            # First call (forward install) fails; second (rollback reinstall) succeeds
            return (1 if pip_call_count == 1 else 0), "", "ERROR: dep conflict"
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        result = await svc.apply_update()

    assert result["success"] is False
    assert "Rollback" in result["error"]
    assert reset_to_rollback, "rollback must run git reset --hard <oldcommit>"
    assert pip_call_count == 2, "rollback must reinstall deps with the old pyproject"
    # restart was never reached
    svc.restart.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_update_exception_rollback_does_not_reinstall(
    svc: SystemService, install_dir: Path
) -> None:
    """If pull itself raises, pip step hasn't run — rollback must NOT reinstall deps."""
    venv_pip = install_dir / ".venv" / "bin" / "pip"
    venv_pip.parent.mkdir(parents=True)
    venv_pip.touch()

    pip_calls = 0
    reset_calls = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal pip_calls, reset_calls
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                return 0, "oldcommit\n", ""
            if op == "pull":
                raise RuntimeError("network down")
            if op == "reset":
                reset_calls += 1
                return 0, "", ""
            return 0, "", ""
        if "pip" in cmd[0]:
            pip_calls += 1
            return 0, "", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        result = await svc.apply_update()

    assert result["success"] is False
    assert reset_calls >= 1  # at least the rollback reset
    assert pip_calls == 0, "pip must not run during pre-pip rollback"


@pytest.mark.asyncio
async def test_concurrent_apply_is_serialised(svc: SystemService) -> None:
    """Two concurrent apply_update calls must not run git in parallel."""
    concurrent = 0
    peak = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await asyncio.sleep(0.02)  # simulate work
        concurrent -= 1
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                return 0, "abc\n", ""
            if op == "diff":
                return 0, "", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        results = await asyncio.gather(svc.apply_update(), svc.apply_update())

    assert all(r["success"] for r in results)
    assert peak == 1, f"update calls must be serialised, saw {peak} concurrent subprocesses"


@pytest.mark.asyncio
async def test_check_update_waits_for_apply(svc: SystemService) -> None:
    """check_update takes the same lock as apply_update."""
    apply_started = asyncio.Event()
    apply_may_finish = asyncio.Event()
    order: list[str] = []

    async def fake_async_run(cmd, timeout=None):
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "fetch":
                order.append("check-fetch")
                return 0, "", ""
            if op == "rev-parse":
                order.append("apply-revparse")
                apply_started.set()
                await apply_may_finish.wait()
                return 0, "abc\n", ""
            if op == "show":
                return 0, 'version = "1.2.3"\n', ""
            if op == "log":
                return 0, "", ""
            if op == "diff":
                return 0, "", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        apply_task = asyncio.create_task(svc.apply_update())
        await apply_started.wait()
        # check_update started while apply holds the lock — must not fetch yet
        check_task = asyncio.create_task(svc.check_update())
        await asyncio.sleep(0.05)
        assert "check-fetch" not in order
        apply_may_finish.set()
        await asyncio.gather(apply_task, check_task)

    assert order.index("apply-revparse") < order.index("check-fetch")
