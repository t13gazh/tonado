"""GPIO button hardware abstraction layer.

Provides scanning (detect which GPIO a button is on) and listening
(runtime edge detection for configured buttons).

Uses gpiod v2 API on Raspberry Pi with lazy imports (same pattern as
spidev/smbus2 in rfid.py/gyro.py).
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class ButtonAction(StrEnum):
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    PLAY_PAUSE = "play_pause"
    NEXT_TRACK = "next_track"
    PREV_TRACK = "previous_track"


@dataclass
class ButtonConfig:
    """A single button's GPIO assignment."""

    action: ButtonAction
    gpio: int


@dataclass
class ScanResult:
    """Result of a single-button scan."""

    gpio: int | None = None
    detected: bool = False


# ---------------------------------------------------------------------------
# Abstract interfaces
# ---------------------------------------------------------------------------


class GpioButtonScanner(ABC):
    """Abstract base for GPIO button scanning during setup."""

    @abstractmethod
    async def start_scan(self, free_gpios: list[int]) -> None:
        """Begin watching all free GPIOs for a button press."""

    @abstractmethod
    async def get_result(self, timeout: float = 15.0) -> ScanResult:
        """Wait for a FALLING edge on any watched GPIO. Returns which one."""

    @abstractmethod
    async def stop_scan(self) -> None:
        """Stop watching GPIOs."""


class GpioButtonListener(ABC):
    """Abstract base for runtime button listening."""

    @abstractmethod
    async def start(self, buttons: list[ButtonConfig]) -> None:
        """Start listening for configured button presses."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and release GPIO resources."""

    @abstractmethod
    def set_callback(self, callback) -> None:
        """Set async callback: callback(action: ButtonAction)."""


# ---------------------------------------------------------------------------
# Real implementations (gpiod v2)
# ---------------------------------------------------------------------------


class GpiodButtonScanner(GpioButtonScanner):
    """GPIO button scanner using libgpiod (gpiod Python bindings).

    Uses gpiod v2 API: request lines with edge detection,
    then wait for events.
    """

    def __init__(self, chip: str = "/dev/gpiochip0") -> None:
        self._chip_path = chip
        self._request = None  # gpiod.LineRequest
        self._free_gpios: list[int] = []

    async def start_scan(self, free_gpios: list[int]) -> None:
        import datetime

        import gpiod
        from gpiod.line import Bias, Edge

        # Release previous scan if still active
        if self._request:
            self._request.release()
            self._request = None

        chip = gpiod.Chip(self._chip_path)
        settings = gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT,
            bias=Bias.PULL_UP,
            edge_detection=Edge.FALLING,
            debounce_period=datetime.timedelta(milliseconds=50),
        )

        # Try each GPIO individually — skip kernel-busy ones
        available = []
        for gpio in free_gpios:
            try:
                test_req = chip.request_lines(
                    consumer="tonado-scan-probe",
                    config={gpio: settings},
                )
                test_req.release()
                available.append(gpio)
            except OSError:
                logger.debug("GPIO %d busy (kernel driver), skipping", gpio)

        if not available:
            raise RuntimeError("No GPIO pins available for scanning")

        self._free_gpios = available
        config = {gpio: settings for gpio in available}
        self._request = chip.request_lines(
            consumer="tonado-button-scan",
            config=config,
        )
        logger.info("Button scan started, watching GPIOs: %s", available)

    async def get_result(self, timeout: float = 15.0) -> ScanResult:
        import datetime

        if not self._request:
            return ScanResult()

        loop = asyncio.get_running_loop()

        def _wait_sync() -> ScanResult:
            if self._request.wait_edge_events(
                timeout=datetime.timedelta(seconds=timeout)
            ):
                events = self._request.read_edge_events()
                if events:
                    gpio = events[0].line_offset
                    return ScanResult(gpio=gpio, detected=True)
            return ScanResult()

        return await loop.run_in_executor(None, _wait_sync)

    async def stop_scan(self) -> None:
        if self._request:
            self._request.release()
            self._request = None
        logger.info("Button scan stopped")


class GpiodButtonListener(GpioButtonListener):
    """Runtime GPIO button listener using libgpiod.

    Continuously watches configured GPIOs for FALLING edges
    and invokes the callback with the mapped action.
    """

    def __init__(self, chip: str = "/dev/gpiochip0") -> None:
        self._chip_path = chip
        self._request = None
        self._gpio_to_action: dict[int, ButtonAction] = {}
        self._callback = None
        self._poll_task: asyncio.Task | None = None

    async def start(self, buttons: list[ButtonConfig]) -> None:
        if not buttons:
            logger.info("No buttons configured, listener not started")
            return

        import datetime

        import gpiod
        from gpiod.line import Bias, Edge

        self._gpio_to_action = {b.gpio: b.action for b in buttons}

        chip = gpiod.Chip(self._chip_path)
        config = {
            b.gpio: gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT,
                bias=Bias.PULL_UP,
                edge_detection=Edge.FALLING,
                debounce_period=datetime.timedelta(milliseconds=50),
            )
            for b in buttons
        }

        self._request = chip.request_lines(
            consumer="tonado-buttons",
            config=config,
        )

        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Button listener started: %s",
            {b.gpio: b.action.value for b in buttons},
        )

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._request:
            self._request.release()
            self._request = None

    def set_callback(self, callback) -> None:
        self._callback = callback

    async def _poll_loop(self) -> None:
        """Wait for edge events in a loop."""
        import datetime

        while True:
            try:
                loop = asyncio.get_running_loop()

                def _wait() -> int | None:
                    if self._request.wait_edge_events(
                        timeout=datetime.timedelta(seconds=1)
                    ):
                        events = self._request.read_edge_events()
                        if events:
                            return events[0].line_offset
                    return None

                gpio = await loop.run_in_executor(None, _wait)
                if gpio is not None and gpio in self._gpio_to_action:
                    action = self._gpio_to_action[gpio]
                    logger.debug("Button press: GPIO %d -> %s", gpio, action)
                    if self._callback:
                        await self._callback(action)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Button listener error: %s", e)
                await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Mock implementations (Windows development)
# ---------------------------------------------------------------------------


class MockGpioButtonScanner(GpioButtonScanner):
    """Mock scanner for Windows development."""

    def __init__(self) -> None:
        self._scanning = False
        self._pending_result: ScanResult | None = None
        self._event: asyncio.Event | None = None

    async def start_scan(self, free_gpios: list[int]) -> None:
        self._scanning = True
        self._event = asyncio.Event()
        self._pending_result = None
        logger.info("Mock button scan started (GPIOs: %s)", free_gpios)

    async def get_result(self, timeout: float = 15.0) -> ScanResult:
        if self._event is None:
            return ScanResult()
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return self._pending_result or ScanResult()
        except asyncio.TimeoutError:
            return ScanResult()

    async def stop_scan(self) -> None:
        self._scanning = False
        if self._event is not None:
            self._event.set()
        logger.info("Mock button scan stopped")

    def simulate_press(self, gpio: int) -> None:
        """Simulate a button press on a specific GPIO (for dev/testing)."""
        self._pending_result = ScanResult(gpio=gpio, detected=True)
        if self._event is not None:
            self._event.set()


class MockGpioButtonListener(GpioButtonListener):
    """Mock listener for Windows development."""

    def __init__(self) -> None:
        self._callback = None
        self._buttons: list[ButtonConfig] = []

    async def start(self, buttons: list[ButtonConfig]) -> None:
        self._buttons = buttons
        logger.info("Mock button listener started: %d buttons", len(buttons))

    async def stop(self) -> None:
        logger.info("Mock button listener stopped")

    def set_callback(self, callback) -> None:
        self._callback = callback

    async def simulate_press(self, action: ButtonAction) -> None:
        """Simulate a button press (for dev/testing)."""
        if self._callback:
            await self._callback(action)
