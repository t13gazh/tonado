"""Card service managing RFID card detection and card-to-content mapping."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiosqlite

from core.hardware.rfid import RfidReader
from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS cards (
    card_id TEXT PRIMARY KEY,
    name TEXT,
    content_type TEXT NOT NULL,
    content_path TEXT NOT NULL,
    cover_path TEXT,
    resume_position REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass
class CardMapping:
    card_id: str
    name: str
    content_type: str  # "folder", "stream", "podcast", "command"
    content_path: str
    cover_path: str | None = None
    resume_position: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "content_type": self.content_type,
            "content_path": self.content_path,
            "cover_path": self.cover_path,
            "resume_position": self.resume_position,
        }


class CardService:
    """Manages RFID card scanning and card-to-content mappings.

    Behavior:
    - Same card re-scanned within cooldown: ignored
    - Same card after cooldown: content restarts
    - Different card: immediate switch
    - Card removed: configurable (pause or continue)
    - Unknown card: nothing happens
    """

    def __init__(
        self,
        reader: RfidReader,
        event_bus: EventBus,
        db: aiosqlite.Connection,
        rescan_cooldown: float = 2.0,
        remove_pauses: bool = False,
    ) -> None:
        self._reader = reader
        self._event_bus = event_bus
        self._db = db
        self._rescan_cooldown = rescan_cooldown
        self._remove_pauses = remove_pauses
        self._scan_task: asyncio.Task | None = None
        self._last_card_id: str | None = None
        self._last_scan_time: float = 0.0
        self._card_on_reader: bool = False
        self._active_card_id: str | None = None  # Card currently "playing" — don't re-trigger
        self._no_card_count: int = 0
        self._remove_threshold: int = 15  # ~3s at 5 Hz poll rate
        self._scan_waiters: list[asyncio.Future[str]] = []

    async def start(self) -> None:
        """Initialize card table and start scanning loop."""
        await self._db.execute(_INIT_SQL)
        await self._db.commit()
        await self._reader.start()
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info("Card service started")

    async def stop(self) -> None:
        """Stop scanning and release reader."""
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        await self._reader.stop()

    async def _scan_loop(self) -> None:
        """Continuously poll the RFID reader.

        RC522 returns None intermittently even with a card present.
        Debounce logic:
        - Card read: if different from active card → trigger event
        - No card: after _remove_threshold consecutive misses → card removed
        - Same card continuously present → only triggers once
        """
        while True:
            try:
                card_id = await self._reader.read_card()
                now = time.monotonic()

                if card_id is not None:
                    self._no_card_count = 0
                    self._card_on_reader = True

                    if card_id != self._active_card_id:
                        # New card or different card swapped in
                        self._active_card_id = card_id
                        await self._handle_card_placed(card_id, now)
                else:
                    if self._card_on_reader:
                        self._no_card_count += 1
                        if self._no_card_count >= self._remove_threshold:
                            self._card_on_reader = False
                            self._no_card_count = 0
                            self._active_card_id = None
                            await self._handle_card_removed()

                await asyncio.sleep(0.2)  # Poll at 5 Hz
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Card scan error: %s", e)
                await asyncio.sleep(1)

    async def _handle_card_placed(self, card_id: str, now: float) -> None:
        """Handle a card being placed on the reader."""
        # Cooldown check for same card
        if card_id == self._last_card_id:
            elapsed = now - self._last_scan_time
            if elapsed < self._rescan_cooldown:
                return

        self._last_card_id = card_id
        self._last_scan_time = now

        # Notify any wizard waiters
        for future in self._scan_waiters:
            if not future.done():
                future.set_result(card_id)
        self._scan_waiters.clear()

        mapping = await self.get_mapping(card_id)
        if mapping is None:
            # Unknown card — do nothing (no sound, no notification)
            logger.info("Unknown card: %s", card_id)
            await self._event_bus.publish("card_unknown", card_id=card_id)
            return

        logger.info("Card scanned: %s → %s", card_id, mapping.name)
        await self._event_bus.publish(
            "card_scanned",
            card_id=card_id,
            mapping=mapping.to_dict(),
        )

    async def _handle_card_removed(self) -> None:
        """Handle card removal from reader."""
        logger.info("Card removed: %s", self._last_card_id)
        await self._event_bus.publish(
            "card_removed",
            card_id=self._last_card_id,
            should_pause=self._remove_pauses,
        )

    # --- CRUD operations ---

    async def get_mapping(self, card_id: str) -> CardMapping | None:
        """Get the content mapping for a card."""
        cursor = await self._db.execute(
            "SELECT card_id, name, content_type, content_path, cover_path, resume_position "
            "FROM cards WHERE card_id = ?",
            (card_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return CardMapping(
            card_id=row[0],
            name=row[1],
            content_type=row[2],
            content_path=row[3],
            cover_path=row[4],
            resume_position=row[5] or 0.0,
        )

    async def set_mapping(self, mapping: CardMapping) -> None:
        """Create or update a card mapping."""
        await self._db.execute(
            "INSERT OR REPLACE INTO cards (card_id, name, content_type, content_path, cover_path, resume_position) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                mapping.card_id,
                mapping.name,
                mapping.content_type,
                mapping.content_path,
                mapping.cover_path,
                mapping.resume_position,
            ),
        )
        await self._db.commit()

    async def delete_mapping(self, card_id: str) -> bool:
        """Delete a card mapping. Returns True if card existed."""
        cursor = await self._db.execute("DELETE FROM cards WHERE card_id = ?", (card_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_mappings(self) -> list[CardMapping]:
        """List all card mappings."""
        cursor = await self._db.execute(
            "SELECT card_id, name, content_type, content_path, cover_path, resume_position "
            "FROM cards ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [
            CardMapping(
                card_id=row[0],
                name=row[1],
                content_type=row[2],
                content_path=row[3],
                cover_path=row[4],
                resume_position=row[5] or 0.0,
            )
            for row in rows
        ]

    async def update_resume_position(self, card_id: str, position: float) -> None:
        """Update the resume position for a card (audiobook progress)."""
        await self._db.execute(
            "UPDATE cards SET resume_position = ? WHERE card_id = ?",
            (position, card_id),
        )
        await self._db.commit()

    async def wait_for_scan(self, timeout: float = 30.0) -> str | None:
        """Wait for the next card to be scanned. Used by the card wizard.

        Returns card_id or None on timeout.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._scan_waiters.append(future)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._scan_waiters.remove(future) if future in self._scan_waiters else None
            return None
