"""RFID reader hardware abstraction layer.

Provides a common interface for RC522 (SPI), PN532 (I2C), USB HID readers,
and a mock implementation for development.
"""

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class RfidReader(ABC):
    """Abstract base class for RFID readers."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize the reader hardware."""

    @abstractmethod
    async def stop(self) -> None:
        """Release hardware resources."""

    @abstractmethod
    async def read_card(self) -> str | None:
        """Read a card UID. Returns hex string or None if no card present."""

    @abstractmethod
    async def card_present(self) -> bool:
        """Check if a card is currently on the reader."""


class MockRfidReader(RfidReader):
    """Mock RFID reader for development without hardware."""

    def __init__(self) -> None:
        self._current_card: str | None = None

    async def start(self) -> None:
        logger.info("Mock RFID reader started")

    async def stop(self) -> None:
        logger.info("Mock RFID reader stopped")

    async def read_card(self) -> str | None:
        return self._current_card

    async def card_present(self) -> bool:
        return self._current_card is not None

    def simulate_card(self, card_id: str | None) -> None:
        """Simulate placing or removing a card (for testing/dev)."""
        self._current_card = card_id


class Rc522Reader(RfidReader):
    """RC522 RFID reader via SPI (spidev)."""

    def __init__(self, bus: int = 0, device: int = 0) -> None:
        self._bus = bus
        self._device = device
        self._spi = None
        self._last_uid: str | None = None

    async def start(self) -> None:
        try:
            import spidev
            self._spi = spidev.SpiDev()
            self._spi.open(self._bus, self._device)
            self._spi.max_speed_hz = 1000000
            logger.info("RC522 reader started on SPI bus %d device %d", self._bus, self._device)
        except ImportError:
            raise RuntimeError("spidev not available — install with: pip install spidev")

    async def stop(self) -> None:
        if self._spi:
            self._spi.close()
            self._spi = None

    async def read_card(self) -> str | None:
        # RC522 communication runs in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_sync)

    async def card_present(self) -> bool:
        uid = await self.read_card()
        return uid is not None

    def _read_sync(self) -> str | None:
        """Synchronous RC522 read via MFRC522 protocol."""
        if not self._spi:
            return None
        try:
            # Write Request command (REQA)
            self._write_register(0x0D, 0x07)  # BitFramingReg
            result = self._transceive([0x26])  # REQA
            if result is None:
                self._last_uid = None
                return None

            # Anti-collision
            result = self._transceive([0x93, 0x20])
            if result is None or len(result) < 4:
                self._last_uid = None
                return None

            uid = "".join(f"{b:02x}" for b in result[:4])
            self._last_uid = uid
            return uid
        except Exception as e:
            logger.debug("RC522 read error: %s", e)
            return None

    def _write_register(self, reg: int, value: int) -> None:
        assert self._spi is not None
        self._spi.xfer2([(reg << 1) & 0x7E, value])

    def _read_register(self, reg: int) -> int:
        assert self._spi is not None
        result = self._spi.xfer2([((reg << 1) & 0x7E) | 0x80, 0])
        return result[1]

    def _transceive(self, data: list[int]) -> list[int] | None:
        """Send data and receive response from card."""
        assert self._spi is not None
        # Simplified MFRC522 transceive — full implementation handles IRQ/timeouts
        self._write_register(0x01, 0x00)  # Idle
        self._write_register(0x0A, 0x80)  # Clear FIFO
        for byte in data:
            self._write_register(0x09, byte)  # FIFO data
        self._write_register(0x01, 0x0C)  # Transceive
        self._write_register(0x0D, self._read_register(0x0D) | 0x80)  # StartSend

        # Wait for completion (simplified)
        for _ in range(100):
            irq = self._read_register(0x04)
            if irq & 0x30:
                break
        else:
            return None

        error = self._read_register(0x06)
        if error & 0x1B:
            return None

        n = self._read_register(0x0A)
        return [self._read_register(0x09) for _ in range(n)]


class Pn532Reader(RfidReader):
    """PN532 RFID reader via I2C (smbus2)."""

    def __init__(self, bus: int = 1, address: int = 0x24) -> None:
        self._bus_num = bus
        self._address = address
        self._bus = None

    async def start(self) -> None:
        try:
            import smbus2
            self._bus = smbus2.SMBus(self._bus_num)
            logger.info("PN532 reader started on I2C bus %d address 0x%02x", self._bus_num, self._address)
        except ImportError:
            raise RuntimeError("smbus2 not available — install with: pip install smbus2")

    async def stop(self) -> None:
        if self._bus:
            self._bus.close()
            self._bus = None

    async def read_card(self) -> str | None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_sync)

    async def card_present(self) -> bool:
        uid = await self.read_card()
        return uid is not None

    def _read_sync(self) -> str | None:
        if not self._bus:
            return None
        try:
            # Send InListPassiveTarget command
            cmd = [0x01, 0x00, 0xFF, 0x04, 0xFC, 0xD4, 0x4A, 0x01, 0x00, 0xE1, 0x00]
            self._bus.write_i2c_block_data(self._address, 0x01, cmd)

            import time
            time.sleep(0.1)

            # Read response
            data = self._bus.read_i2c_block_data(self._address, 0x01, 20)
            # Parse UID from response (simplified)
            if len(data) > 12 and data[6] == 0xD5 and data[7] == 0x4B:
                uid_length = data[12]
                if uid_length > 0 and len(data) > 12 + uid_length:
                    uid_bytes = data[13 : 13 + uid_length]
                    return "".join(f"{b:02x}" for b in uid_bytes)
            return None
        except Exception as e:
            logger.debug("PN532 read error: %s", e)
            return None


class UsbHidReader(RfidReader):
    """USB HID RFID reader (keyboard emulation).

    These readers type the card UID as keyboard input followed by Enter.
    We read from the HID device directly.
    """

    def __init__(self, device_path: str = "/dev/hidraw0") -> None:
        self._device_path = device_path
        self._file = None
        self._last_uid: str | None = None

    async def start(self) -> None:
        try:
            self._file = open(self._device_path, "rb")  # noqa: SIM115
            logger.info("USB HID reader started on %s", self._device_path)
        except FileNotFoundError:
            raise RuntimeError(f"USB HID device not found: {self._device_path}")

    async def stop(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    async def read_card(self) -> str | None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_sync)

    async def card_present(self) -> bool:
        return self._last_uid is not None

    def _read_sync(self) -> str | None:
        if not self._file:
            return None
        try:
            import select
            ready, _, _ = select.select([self._file], [], [], 0.1)
            if not ready:
                return self._last_uid

            data = self._file.read(8)
            if not data:
                return None

            # HID keyboard reports: [modifier, reserved, key1, key2, ...]
            # Map HID keycodes to characters
            key = data[2] if len(data) > 2 else 0
            if key == 0x28:  # Enter — end of UID
                uid = self._last_uid
                return uid
            elif key > 0:
                char = self._hid_to_char(key)
                if char:
                    if self._last_uid is None:
                        self._last_uid = ""
                    self._last_uid += char
            return None
        except Exception as e:
            logger.debug("USB HID read error: %s", e)
            return None

    @staticmethod
    def _hid_to_char(keycode: int) -> str | None:
        """Convert HID keycode to character."""
        # Number keys 1-9, 0
        if 0x1E <= keycode <= 0x26:
            return str((keycode - 0x1E + 1) % 10)
        if keycode == 0x27:
            return "0"
        # Letters a-f (for hex UIDs)
        if 0x04 <= keycode <= 0x09:
            return chr(keycode - 0x04 + ord("a"))
        return None


def detect_reader(hardware_mode: str = "auto") -> RfidReader:
    """Detect and return the appropriate RFID reader.

    Args:
        hardware_mode: "auto", "mock", "rc522", "pn532", "usb", or "pi" (auto-detect on Pi)
    """
    if hardware_mode == "mock":
        return MockRfidReader()

    if hardware_mode == "rc522":
        return Rc522Reader()

    if hardware_mode == "pn532":
        return Pn532Reader()

    if hardware_mode == "usb":
        return UsbHidReader()

    # Auto-detection
    if hardware_mode in ("auto", "pi"):
        # Try SPI (RC522)
        try:
            import spidev  # noqa: F401
            from pathlib import Path
            if Path("/dev/spidev0.0").exists():
                logger.info("Auto-detected RC522 (SPI)")
                return Rc522Reader()
        except ImportError:
            pass

        # Try I2C (PN532)
        try:
            import smbus2  # noqa: F401
            from pathlib import Path
            if Path("/dev/i2c-1").exists():
                logger.info("Auto-detected PN532 (I2C)")
                return Pn532Reader()
        except ImportError:
            pass

        # Try USB HID
        from pathlib import Path
        if Path("/dev/hidraw0").exists():
            logger.info("Auto-detected USB HID reader")
            return UsbHidReader()

    # Fallback to mock
    logger.info("No RFID hardware detected, using mock reader")
    return MockRfidReader()
