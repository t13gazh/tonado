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
        return proc.returncode or 0, stdout.decode(), stderr.decode()
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"
    except asyncio.TimeoutError:
        proc.kill()  # type: ignore[union-attr]
        return 1, "", f"Command timed out after {timeout}s"
