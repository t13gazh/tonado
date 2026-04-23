"""Tests for the system/update service — K5 hardening."""

import asyncio
import logging
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
    revparse_count = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal revparse_count
        calls.append(tuple(cmd))
        # cmd shape: ["git", "-C", <install_dir>, <op>, ...]
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            # rev-parse HEAD is called twice: once before pull, once after.
            # Return distinct hashes so the "no changes" shortcut is not taken.
            if op == "rev-parse":
                revparse_count += 1
                return 0, ("abc123\n" if revparse_count == 1 else "def456\n"), ""
            if op == "reset":
                return 0, "", ""
            if op == "clean":
                return 0, "", ""
            if op == "pull":
                return 0, "Updating\n", ""
            if op == "diff":
                # No pyproject.toml changed
                return 0, "README.md\nweb/build/app.js\n", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        result = await svc.apply_update()

    assert result["success"] is True
    assert result["new_commit_hash"] == "def456"
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
    revparse_count = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal reset_to_rollback, pip_call_count, revparse_count
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                # First call (pre-pull): old hash; second (post-pull): new hash
                revparse_count += 1
                return 0, ("oldcommit\n" if revparse_count == 1 else "newcommit\n"), ""
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
    # Toggle old/new hashes per apply_update invocation (pre/post pull).
    # Keeping them equal inside a single call would take the "no changes"
    # shortcut and skip the diff path we want to exercise here.
    revparse_seq = iter(["a\n", "b\n", "c\n", "d\n"])

    async def fake_async_run(cmd, timeout=None):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await asyncio.sleep(0.02)  # simulate work
        concurrent -= 1
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                return 0, next(revparse_seq), ""
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
    revparse_count = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal revparse_count
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "fetch":
                order.append("check-fetch")
                return 0, "", ""
            if op == "rev-parse":
                revparse_count += 1
                if revparse_count == 1:
                    order.append("apply-revparse")
                    apply_started.set()
                    await apply_may_finish.wait()
                    return 0, "abc\n", ""
                # Post-pull rev-parse: return a different hash so the
                # apply path continues past the "no changes" shortcut.
                return 0, "def\n", ""
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


@pytest.mark.asyncio
async def test_apply_update_pip_timeout_rolls_back(
    svc: SystemService, install_dir: Path
) -> None:
    """pip returning a timeout-failure (rc=1) triggers rollback to old hash."""
    venv_pip = install_dir / ".venv" / "bin" / "pip"
    venv_pip.parent.mkdir(parents=True)
    venv_pip.touch()

    reset_to_rollback = False
    pip_timeout_seen = False
    revparse_count = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal reset_to_rollback, pip_timeout_seen, revparse_count
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                revparse_count += 1
                return 0, ("oldcommit\n" if revparse_count == 1 else "newcommit\n"), ""
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
            # Simulate the timeout path: async_run maps TimeoutError to
            # (1, "", "Command timed out after ...s"). Rollback pip
            # (second call) is allowed to succeed.
            if not pip_timeout_seen:
                pip_timeout_seen = True
                # Assert the caller passed a generous timeout
                assert timeout is not None and timeout >= 300, (
                    f"pip install must use a generous timeout, got {timeout}"
                )
                return 1, "", "Command timed out after 600s"
            return 0, "", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        result = await svc.apply_update()

    assert result["success"] is False
    assert "Rollback" in result["error"]
    assert pip_timeout_seen, "pip install must have been attempted"
    assert reset_to_rollback, "rollback must run git reset --hard <oldcommit>"
    svc.restart.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_update_already_up_to_date(svc: SystemService) -> None:
    """HEAD unchanged after pull → success, no_changes=True, no restart, no pip."""
    calls: list[tuple] = []

    async def fake_async_run(cmd, timeout=None):
        calls.append(tuple(cmd))
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                # Both pre- and post-pull return the same hash
                return 0, "samehash\n", ""
            if op == "reset":
                return 0, "", ""
            if op == "clean":
                return 0, "", ""
            if op == "pull":
                return 0, "Already up to date.\n", ""
            if op == "diff":
                return 0, "", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        result = await svc.apply_update()

    assert result["success"] is True
    assert result["no_changes"] is True
    assert result["files_changed"] == 0
    assert result["new_commit_hash"] == "samehash"
    svc.restart.assert_not_awaited()
    # Neither pip nor `git diff` need to run when HEAD didn't move
    assert not any("pip" in " ".join(c) for c in calls)
    assert not any(c[:2] == ("git", "-C") and c[3] == "diff" for c in calls)


@pytest.mark.asyncio
async def test_apply_update_reset_fails_aborts_early(svc: SystemService) -> None:
    """If the pre-pull `git reset --hard HEAD` fails, abort before pulling."""
    saw_pull = False

    async def fake_async_run(cmd, timeout=None):
        nonlocal saw_pull
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                return 0, "oldcommit\n", ""
            if op == "reset":
                # reset --hard HEAD — fails hard
                return 1, "", "fatal: unable to unlink 'web/build/app.js'"
            if op == "pull":
                saw_pull = True
                return 0, "", ""
        return 0, "", ""

    with patch("core.services.system_service.async_run", side_effect=fake_async_run):
        result = await svc.apply_update()

    assert result["success"] is False
    assert "Reset" in result["error"]
    assert not saw_pull, "pull must not run after reset failure"
    svc.restart.assert_not_awaited()


@pytest.mark.asyncio
async def test_rollback_git_reset_failure_is_logged(
    svc: SystemService, install_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When rollback's `git reset --hard <hash>` fails, log hash + rc + stderr."""
    venv_pip = install_dir / ".venv" / "bin" / "pip"
    venv_pip.parent.mkdir(parents=True)
    venv_pip.touch()

    revparse_count = 0

    async def fake_async_run(cmd, timeout=None):
        nonlocal revparse_count
        if cmd[:2] == ["git", "-C"]:
            op = cmd[3]
            if op == "rev-parse":
                revparse_count += 1
                return 0, ("oldcommit\n" if revparse_count == 1 else "newcommit\n"), ""
            if op == "reset":
                if cmd[-1] == "oldcommit":
                    # Rollback reset: fail
                    return 1, "", "fatal: reference broken"
                # Pre-pull reset: succeed
                return 0, "", ""
            if op == "clean":
                return 0, "", ""
            if op == "pull":
                return 0, "Fast-forward", ""
            if op == "diff":
                return 0, "pyproject.toml\n", ""
        if "pip" in cmd[0]:
            # Trigger the rollback path by failing the forward pip install
            return 1, "", "dep conflict"
        return 0, "", ""

    with caplog.at_level(logging.ERROR, logger="core.services.system_service"):
        with patch(
            "core.services.system_service.async_run", side_effect=fake_async_run
        ):
            result = await svc.apply_update()

    assert result["success"] is False
    # Expect a rollback-reset error record that mentions hash, rc, and stderr
    rollback_records = [
        r for r in caplog.records if "Rollback" in r.getMessage()
    ]
    assert rollback_records, "rollback reset failure must be logged"
    msg = next(
        (r.getMessage() for r in rollback_records if "git reset" in r.getMessage()),
        "",
    )
    assert "oldcommit" in msg, f"rollback log must include hash, got: {msg!r}"
    assert "rc=1" in msg, f"rollback log must include rc, got: {msg!r}"
    assert "reference broken" in msg, f"rollback log must include stderr, got: {msg!r}"
