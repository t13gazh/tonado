"""Card service managing RFID card detection and card-to-content mapping."""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass

import aiosqlite

from core.hardware.rfid import RfidReader
from core.schemas.common import ContentType
from core.services.base import BaseService
from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)


@dataclass
class CardMapping:
    card_id: str
    name: str
    content_type: ContentType
    content_path: str
    cover_path: str | None = None
    resume_position: float = 0.0



class CardService(BaseService):
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
        config_service: "ConfigService | None" = None,
        rescan_cooldown: float = 2.0,
        remove_pauses: bool = False,
        reader_connected: bool = False,
    ) -> None:
        super().__init__()
        self._reader = reader
        self._event_bus = event_bus
        self._db = db
        self._config_service = config_service
        self._rescan_cooldown = rescan_cooldown
        self._remove_pauses = remove_pauses
        self._reader_connected: bool = reader_connected
        self._scan_task: asyncio.Task | None = None
        self._last_card_id: str | None = None
        self._last_scan_time: float = 0.0
        self._card_on_reader: bool = False
        self._active_card_id: str | None = None  # Card currently "playing" — don't re-trigger
        self._no_card_count: int = 0
        self._remove_threshold: int = 15  # ~3s at 5 Hz poll rate
        self._scan_waiters: list[asyncio.Future[str]] = []

    async def start(self) -> None:
        """Start RFID scanning loop (schema managed by DatabaseManager)."""
        try:
            await self._reader.start()
        except Exception as e:
            logger.warning("RFID reader init failed, card service disabled: %s", e)
            self._reader_connected = False
            return
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

    def health(self) -> dict:
        """Return RFID reader health status based on detection result."""
        reader_type = type(self._reader).__name__
        if not self._reader_connected:
            return {"status": "not_configured", "detail": "Kein RFID-Reader erkannt"}
        return {"status": "connected", "detail": reader_type}

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
            mapping=asdict(mapping),
        )

    async def _handle_card_removed(self) -> None:
        """Handle card removal from reader."""
        logger.info("Card removed: %s", self._last_card_id)
        # Read current config value (may have changed at runtime)
        should_pause = self._remove_pauses
        if self._config_service:
            val = await self._config_service.get("card.remove_pauses")
            if val is not None:
                should_pause = bool(val)
        await self._event_bus.publish(
            "card_removed",
            card_id=self._last_card_id,
            should_pause=should_pause,
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

    async def wait_for_scan(self, timeout: float = 30.0, new_only: bool = False) -> str | None:
        """Wait for a card to be scanned. Used by the card wizard.

        If new_only=False and a card is already on the reader, returns immediately.
        If new_only=True, always waits for a new card placement event.
        """
        if not new_only and self._card_on_reader and self._active_card_id:
            return self._active_card_id

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._scan_waiters.append(future)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            # Always clean up — covers timeout, cancellation, and other errors
            if future in self._scan_waiters:
                self._scan_waiters.remove(future)
