"""Async subprocess utilities replacing sync subprocess.run calls."""

import asyncio


async def async_run(
    cmd: list[str], *, timeout: float = 30
) -> tuple[int, str, str]:
    """Run a command asynchronously and return (returncode, stdout, stderr).

    Returns returncode 1 and empty output if the command is not found.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        # Some system tools (Windows `hostname -I`, some NetworkManager
        # locales) emit non-UTF-8 bytes. Don't crash the whole call when
        # we only need the rough textual output.
        return (
            proc.returncode or 0,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"
    except asyncio.TimeoutError:
        # wait_for cancels the communicate() coroutine but NOT the subprocess
        # itself — without an explicit kill+wait the child becomes a zombie
        # (PID leak). Real pain on a Pi Zero W where pip install regularly
        # bumps the 600s timeout.
        proc.kill()  # type: ignore[union-attr]
        try:
            await proc.wait()  # type: ignore[union-attr]
        except Exception:
            # Best-effort reap — don't mask the original timeout failure.
            pass
        return 1, "", f"Command timed out after {timeout}s"
