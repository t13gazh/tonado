"""Mock MPD client for testing PlayerService without a running MPD server.

Simulates the python-mpd2 async client interface with in-memory state.
"""

import asyncio
from typing import Any


class MockMPDClient:
    """In-memory mock of mpd.asyncio.MPDClient."""

    def __init__(self) -> None:
        self._connected = False
        self._state = "stop"  # "play", "pause", "stop"
        self._volume = 50
        self._elapsed = 0.0
        self._duration = 0.0
        self._playlist: list[dict[str, str]] = []
        self._current_song_idx = -1
        self._random = "0"
        self._repeat = "0"
        self._single = "0"
        self._outputs = [
            {"outputid": "0", "outputname": "Default", "outputenabled": "1"},
        ]

    async def connect(self, host: str, port: int) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    async def status(self) -> dict[str, str]:
        result: dict[str, str] = {
            "state": self._state,
            "volume": str(self._volume),
            "elapsed": str(self._elapsed),
            "duration": str(self._duration),
            "random": self._random,
            "repeat": self._repeat,
            "single": self._single,
            "playlistlength": str(len(self._playlist)),
        }
        if self._current_song_idx >= 0:
            result["song"] = str(self._current_song_idx)
        return result

    async def currentsong(self) -> dict[str, str]:
        if 0 <= self._current_song_idx < len(self._playlist):
            return self._playlist[self._current_song_idx]
        return {}

    async def playlistinfo(self) -> list[dict[str, str]]:
        return list(self._playlist)

    async def add(self, uri: str) -> None:
        self._playlist.append({"file": uri, "title": uri.split("/")[-1]})

    async def clear(self) -> None:
        self._playlist.clear()
        self._current_song_idx = -1
        self._state = "stop"

    async def play(self, idx: int = 0) -> None:
        if self._playlist:
            self._current_song_idx = min(idx, len(self._playlist) - 1)
            self._state = "play"
            self._elapsed = 0.0
            song = self._playlist[self._current_song_idx]
            self._duration = float(song.get("duration", "180"))

    async def stop(self) -> None:
        self._state = "stop"
        self._elapsed = 0.0

    async def pause(self, pause: int) -> None:
        self._state = "pause" if pause == 1 else "play"

    async def next(self) -> None:
        if self._current_song_idx < len(self._playlist) - 1:
            self._current_song_idx += 1
            self._elapsed = 0.0
        else:
            raise Exception("No next track")

    async def previous(self) -> None:
        if self._current_song_idx > 0:
            self._current_song_idx -= 1
            self._elapsed = 0.0
        else:
            raise Exception("No previous track")

    async def setvol(self, volume: int) -> None:
        self._volume = max(0, min(100, volume))

    async def seekcur(self, position: float) -> None:
        self._elapsed = position

    async def random(self, state: int) -> None:
        self._random = str(state)

    async def repeat(self, state: int) -> None:
        self._repeat = str(state)

    async def single(self, state: int) -> None:
        self._single = str(state)

    async def outputs(self) -> list[dict[str, str]]:
        return list(self._outputs)

    async def enableoutput(self, output_id: int) -> None:
        for o in self._outputs:
            if int(o["outputid"]) == output_id:
                o["outputenabled"] = "1"

    async def disableoutput(self, output_id: int) -> None:
        for o in self._outputs:
            if int(o["outputid"]) == output_id:
                o["outputenabled"] = "0"

    async def idle(self, subsystems: list[str] | None = None):
        """Simulate idle — just hang forever (tests should cancel this)."""
        await asyncio.sleep(3600)
        yield ["player"]  # Never reached in tests
