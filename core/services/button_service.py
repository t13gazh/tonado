"""Button service — manages GPIO button scanning and runtime listening."""

import asyncio
import json
import logging

from core.hardware.gpio_buttons import (
    ButtonAction,
    ButtonConfig,
    GpioButtonListener,
    GpioButtonScanner,
    ScanResult,
)
from core.services.base import BaseService
from core.services.config_service import ConfigService
from core.services.event_bus import EventBus

logger = logging.getLogger(__name__)

# Config key for stored button mappings
CONFIG_KEY = "hardware.buttons"


class ButtonService(BaseService):
    """Manages GPIO button scanning (setup) and runtime listening.

    Lifecycle:
    - start(): loads saved config, starts listener if buttons configured
    - stop(): stops listener, releases GPIOs

    Scanning (setup wizard):
    - start_scan(free_gpios): begin watching for button press
    - get_scan_result(): wait for result
    - stop_scan(): cancel
    - save_buttons(buttons): persist to config
    """

    def __init__(
        self,
        scanner: GpioButtonScanner,
        listener: GpioButtonListener,
        event_bus: EventBus,
        config_service: ConfigService,
    ) -> None:
        super().__init__()
        self._scanner = scanner
        self._listener = listener
        self._event_bus = event_bus
        self._config = config_service
        self._buttons: list[ButtonConfig] = []
        self._test_mode = False
        self._test_events: list[dict] = []

    @property
    def buttons(self) -> list[ButtonConfig]:
        return self._buttons

    @property
    def has_buttons(self) -> bool:
        return len(self._buttons) > 0

    async def start(self) -> None:
        """Load saved button config and start listener."""
        raw = await self._config.get(CONFIG_KEY)
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                self._buttons = [
                    ButtonConfig(
                        action=ButtonAction(b["action"]),
                        gpio=b["gpio"],
                    )
                    for b in data
                ]
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning("Invalid button config, ignoring: %s", e)
                self._buttons = []

        if self._buttons:
            self._listener.set_callback(self._on_button_press)
            try:
                await self._listener.start(self._buttons)
            except RuntimeError as e:
                logger.error("Could not start button listener: %s", e)
                return
            logger.info("Button service started with %d buttons", len(self._buttons))
        else:
            logger.info("Button service started (no buttons configured)")

    async def stop(self) -> None:
        await self._listener.stop()
        await self._scanner.stop_scan()

    def health(self) -> dict:
        if not self._buttons:
            return {"status": "not_configured", "detail": "Keine Tasten konfiguriert"}
        return {
            "status": "connected",
            "detail": f"{len(self._buttons)} Tasten aktiv",
        }

    # --- Scanning (setup wizard) ---

    async def start_scan(self, free_gpios: list[int]) -> None:
        """Start watching free GPIOs for a button press."""
        await self._scanner.start_scan(free_gpios)

    async def get_scan_result(self, timeout: float = 15.0) -> ScanResult:
        """Wait for scan result with timeout."""
        return await self._scanner.get_result(timeout=timeout)

    async def stop_scan(self) -> None:
        """Cancel current scan."""
        await self._scanner.stop_scan()

    # --- Config persistence ---

    async def save_buttons(self, buttons: list[ButtonConfig]) -> None:
        """Save button config and restart listener."""
        self._buttons = buttons
        data = [{"action": b.action.value, "gpio": b.gpio} for b in buttons]
        await self._config.set(CONFIG_KEY, json.dumps(data))

        # Restart listener with new config
        await self._listener.stop()
        if buttons:
            self._listener.set_callback(self._on_button_press)
            try:
                await self._listener.start(buttons)
            except RuntimeError as e:
                logger.error("Could not start button listener: %s", e)
        logger.info("Button config saved: %d buttons", len(buttons))

    async def clear_buttons(self) -> None:
        """Remove all button config."""
        self._buttons = []
        await self._config.delete(CONFIG_KEY)
        await self._listener.stop()

    def get_config(self) -> list[dict]:
        """Return current config as serializable list."""
        return [{"action": b.action.value, "gpio": b.gpio} for b in self._buttons]

    # --- Test mode (live feedback in wizard) ---

    async def start_test(self, buttons: list[ButtonConfig] | None = None) -> None:
        """Start test mode — button presses are recorded for polling.

        If buttons are provided (from wizard, before save), start a
        temporary listener for those pins.
        """
        self._test_mode = True
        self._test_events = []

        # Stop scanner so its GPIO lines are free for the listener
        await self._scanner.stop_scan()

        # Start temporary listener if buttons provided and listener not running
        if buttons and not self._buttons:
            self._listener.set_callback(self._on_button_press)
            try:
                await self._listener.start(buttons)
                logger.info("Test mode: temporary listener for %d buttons", len(buttons))
            except RuntimeError as e:
                logger.error("Could not start test listener: %s", e)

    def get_test_events(self) -> list[dict]:
        """Get and clear pending test events."""
        events = self._test_events.copy()
        self._test_events.clear()
        return events

    async def stop_test(self) -> None:
        """Stop test mode and temporary listener."""
        self._test_mode = False
        self._test_events = []
        # Stop temporary listener if no permanent buttons configured
        if not self._buttons:
            await self._listener.stop()

    # --- Runtime callback ---

    async def _on_button_press(self, action: ButtonAction) -> None:
        """Handle a physical button press."""
        if self._test_mode:
            self._test_events.append({
                "action": action.value,
                "gpio": next(
                    (b.gpio for b in self._buttons if b.action == action), None
                ),
            })
            return

        logger.info("Button pressed: %s", action)
        await self._event_bus.publish(
            "button_pressed",
            action=action.value,
        )
