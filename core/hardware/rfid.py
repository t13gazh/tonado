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
    """RC522 RFID reader via SPI (spidev).

    Full MFRC522 implementation with proper chip initialization,
    antenna control, and ISO 14443A card communication.
    """

    # MFRC522 registers
    _CMD_REG = 0x01
    _COMIEN_REG = 0x02
    _COMIRQ_REG = 0x04
    _DIVIRQ_REG = 0x05
    _ERROR_REG = 0x06
    _FIFO_DATA_REG = 0x09
    _FIFO_LEVEL_REG = 0x0A
    _CONTROL_REG = 0x0C
    _BIT_FRAMING_REG = 0x0D
    _MODE_REG = 0x11
    _TX_CONTROL_REG = 0x14
    _TX_ASK_REG = 0x15
    _CRC_RESULT_MSB = 0x21
    _CRC_RESULT_LSB = 0x22
    _TMODE_REG = 0x2A
    _TPRESCALER_REG = 0x2B
    _TRELOAD_H_REG = 0x2C
    _TRELOAD_L_REG = 0x2D
    _AUTO_TEST_REG = 0x36
    _VERSION_REG = 0x37

    # MFRC522 commands
    _CMD_IDLE = 0x00
    _CMD_CALCCRC = 0x03
    _CMD_TRANSCEIVE = 0x0C
    _CMD_SOFTRESET = 0x0F

    # PICC commands (ISO 14443A)
    _PICC_REQA = 0x26
    _PICC_ANTICOLL = 0x93
    _PICC_SELECT = 0x93

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
            self._spi.mode = 0  # SPI mode 0
            self._init_chip()
            version = self._read_register(self._VERSION_REG)
            logger.info(
                "RC522 reader started on SPI bus %d device %d (chip version 0x%02x)",
                self._bus, self._device, version,
            )
        except ImportError:
            raise RuntimeError("spidev not available — install with: pip install spidev")

    async def stop(self) -> None:
        if self._spi:
            # Turn off antenna
            self._clear_bitmask(self._TX_CONTROL_REG, 0x03)
            self._spi.close()
            self._spi = None

    async def read_card(self) -> str | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_sync)

    async def card_present(self) -> bool:
        uid = await self.read_card()
        return uid is not None

    def _init_chip(self) -> None:
        """Initialize MFRC522 with proper reset, timer, and antenna config."""
        assert self._spi is not None

        # Soft reset
        self._write_register(self._CMD_REG, self._CMD_SOFTRESET)
        import time
        time.sleep(0.05)

        # Timer: TPrescaler=0x0A9, TReload=0x03E8 → ~25ms timeout
        self._write_register(self._TMODE_REG, 0x8D)       # TAuto=1, prescaler high
        self._write_register(self._TPRESCALER_REG, 0x3E)   # Prescaler low
        self._write_register(self._TRELOAD_H_REG, 0x00)    # Reload high
        self._write_register(self._TRELOAD_L_REG, 0x1E)    # Reload low (30)

        # Force 100% ASK modulation
        self._write_register(self._TX_ASK_REG, 0x40)

        # CRC preset value 0x6363 (ISO 14443A)
        self._write_register(self._MODE_REG, 0x3D)

        # Turn on antenna (TX1 and TX2)
        self._set_bitmask(self._TX_CONTROL_REG, 0x03)

    def _read_sync(self) -> str | None:
        """Synchronous RC522 read via MFRC522 protocol."""
        if not self._spi:
            return None
        try:
            # Step 1: REQA — request any card in field
            self._write_register(self._BIT_FRAMING_REG, 0x07)  # 7 bits for REQA
            result, bits = self._transceive([self._PICC_REQA])
            if result is None or len(result) != 2:
                self._last_uid = None
                return None

            # Step 2: Anti-collision (cascade level 1)
            self._write_register(self._BIT_FRAMING_REG, 0x00)  # Full bytes
            result, bits = self._transceive([self._PICC_ANTICOLL, 0x20])
            if result is None or len(result) != 5:
                self._last_uid = None
                return None

            # Verify BCC (XOR checksum of UID bytes)
            bcc = 0
            for b in result[:4]:
                bcc ^= b
            if bcc != result[4]:
                logger.debug("RC522: BCC mismatch")
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

    def _set_bitmask(self, reg: int, mask: int) -> None:
        current = self._read_register(reg)
        self._write_register(reg, current | mask)

    def _clear_bitmask(self, reg: int, mask: int) -> None:
        current = self._read_register(reg)
        self._write_register(reg, current & ~mask)

    def _transceive(self, data: list[int]) -> tuple[list[int] | None, int]:
        """Send data to card and receive response. Returns (data, valid_bits)."""
        assert self._spi is not None

        self._write_register(self._CMD_REG, self._CMD_IDLE)
        self._write_register(self._COMIRQ_REG, 0x7F)          # Clear all IRQ flags
        self._set_bitmask(self._FIFO_LEVEL_REG, 0x80)         # Flush FIFO

        for byte in data:
            self._write_register(self._FIFO_DATA_REG, byte)

        self._write_register(self._CMD_REG, self._CMD_TRANSCEIVE)
        self._set_bitmask(self._BIT_FRAMING_REG, 0x80)        # StartSend

        # Wait for completion with timeout
        for _ in range(2000):
            irq = self._read_register(self._COMIRQ_REG)
            if irq & 0x30:  # RxIRq or IdleIRq
                break
            if irq & 0x01:  # TimerIRq — timeout
                return None, 0
        else:
            return None, 0

        # Check for errors (BufferOvfl, CollErr, ParityErr, ProtocolErr)
        error = self._read_register(self._ERROR_REG)
        if error & 0x13:  # Buffer overflow, parity, protocol
            return None, 0

        # Read data from FIFO
        n = self._read_register(self._FIFO_LEVEL_REG)
        last_bits = self._read_register(self._CONTROL_REG) & 0x07

        result = [self._read_register(self._FIFO_DATA_REG) for _ in range(n)]
        valid_bits = (n - 1) * 8 + last_bits if last_bits else n * 8

        return result, valid_bits


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
        loop = asyncio.get_running_loop()
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
        loop = asyncio.get_running_loop()
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


def detect_reader(reader_type: str = "auto", device: str = "") -> RfidReader:
    """Create the appropriate RFID reader instance.

    Args:
        reader_type: Explicit type from HardwareDetector profile or settings.
            "rc522", "pn532", "usb" — create reader directly.
            "none", "mock" — return mock reader.
            "auto" — run detect_rfid() from detect.py (real chip probe).
        device: Device path hint (e.g. "/dev/spidev0.0", "/dev/hidraw0").
    """
    if reader_type == "mock":
        return MockRfidReader()

    if reader_type == "none":
        logger.info("No RFID reader configured, using mock reader")
        return MockRfidReader()

    if reader_type == "rc522":
        return Rc522Reader()

    if reader_type == "pn532":
        return Pn532Reader()

    if reader_type == "usb":
        dev = device or "/dev/hidraw0"
        return UsbHidReader(device_path=dev)

    # Auto-detection — delegate to detect.py which does real chip probing
    if reader_type == "auto":
        from core.hardware.detect import detect_rfid
        detected_type, detected_device = detect_rfid()
        if detected_type != "none":
            logger.info("Auto-detected RFID: %s on %s", detected_type, detected_device)
            return detect_reader(reader_type=detected_type, device=detected_device)
        logger.info("No RFID hardware detected, using mock reader")
        return MockRfidReader()

    # Unknown type — fallback to mock
    logger.warning("Unknown reader_type '%s', using mock reader", reader_type)
    return MockRfidReader()
