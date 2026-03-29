"""Hardware auto-detection for Raspberry Pi.

Detects Pi model, RFID reader, audio output, gyro sensor, and GPIO layout.
Returns a structured hardware profile used by the setup wizard.
"""

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PiModel:
    """Detected Raspberry Pi model information."""

    model: str = "unknown"
    revision: str = "unknown"
    ram_mb: int = 0
    has_wifi: bool = False
    has_bluetooth: bool = False
    supported: bool = False


@dataclass
class AudioOutput:
    """Detected audio output configuration."""

    name: str = "unknown"
    type: str = "unknown"  # "analog", "hdmi", "i2s", "usb"
    device: str = ""
    recommended: bool = False


@dataclass
class HardwareProfile:
    """Complete hardware profile of the system."""

    pi: PiModel = field(default_factory=PiModel)
    rfid_reader: str = "none"  # "rc522", "pn532", "usb", "none"
    rfid_device: str = ""
    audio_outputs: list[AudioOutput] = field(default_factory=list)
    gyro_detected: bool = False
    gpio_available: bool = False
    is_mock: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "pi": asdict(self.pi),
            "rfid": {
                "reader": self.rfid_reader,
                "device": self.rfid_device,
            },
            "audio": [asdict(a) for a in self.audio_outputs],
            "gyro_detected": self.gyro_detected,
            "gpio_available": self.gpio_available,
            "is_mock": self.is_mock,
        }


# Pi model lookup by revision code (partial, most common models)
_PI_MODELS: dict[str, tuple[str, int, bool, bool]] = {
    # revision: (model, ram_mb, wifi, bluetooth)
    "9000c1": ("Pi Zero W", 512, True, True),
    "902120": ("Pi Zero 2 W", 512, True, True),
    "a02082": ("Pi 3B", 1024, True, True),
    "a22082": ("Pi 3B", 1024, True, True),
    "a020d3": ("Pi 3B+", 1024, True, True),
    "a03111": ("Pi 4B (1GB)", 1024, True, True),
    "b03111": ("Pi 4B (2GB)", 2048, True, True),
    "b03112": ("Pi 4B (2GB)", 2048, True, True),
    "c03111": ("Pi 4B (4GB)", 4096, True, True),
    "c03112": ("Pi 4B (4GB)", 4096, True, True),
    "d03114": ("Pi 4B (8GB)", 8192, True, True),
    "c04170": ("Pi 5 (4GB)", 4096, True, True),
    "d04170": ("Pi 5 (8GB)", 8192, True, True),
}

# Unsupported models (no WiFi)
_UNSUPPORTED_MODELS = {"Pi B+", "Pi A+", "Pi 2B"}


def detect_pi_model() -> PiModel:
    """Detect the Raspberry Pi model from /proc/cpuinfo."""
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return PiModel()

    try:
        content = cpuinfo.read_text()

        # Extract revision
        revision_match = re.search(r"^Revision\s*:\s*(\w+)$", content, re.MULTILINE)
        if not revision_match:
            return PiModel()

        revision = revision_match.group(1).strip()

        # Extract model name from "Model" line
        model_match = re.search(r"^Model\s*:\s*(.+)$", content, re.MULTILINE)
        model_name = model_match.group(1).strip() if model_match else "unknown"

        # Look up in known models
        info = _PI_MODELS.get(revision)
        if info:
            name, ram, wifi, bt = info
            supported = name not in _UNSUPPORTED_MODELS and wifi
            return PiModel(
                model=name,
                revision=revision,
                ram_mb=ram,
                has_wifi=wifi,
                has_bluetooth=bt,
                supported=supported,
            )

        # Fallback: use model name from cpuinfo
        has_wifi = "Zero W" in model_name or "3" in model_name or "4" in model_name or "5" in model_name
        return PiModel(
            model=model_name,
            revision=revision,
            ram_mb=0,
            has_wifi=has_wifi,
            has_bluetooth=has_wifi,
            supported=has_wifi,
        )

    except Exception as e:
        logger.warning("Could not detect Pi model: %s", e)
        return PiModel()


def detect_rfid() -> tuple[str, str]:
    """Detect connected RFID reader. Returns (type, device_path).

    Checks USB HID first (no config required), then SPI (RC522), then I2C (PN532).
    """
    # Check USB HID first — works without SPI/I2C config
    for i in range(4):
        hidraw = Path(f"/dev/hidraw{i}")
        if hidraw.exists():
            logger.info("RFID: USB HID reader detected on %s", hidraw)
            return "usb", str(hidraw)

    # Check SPI (RC522) — verify chip responds, not just SPI device exists
    spi_device = Path("/dev/spidev0.0")
    if spi_device.exists():
        try:
            import spidev
            spi = spidev.SpiDev()
            spi.open(0, 0)
            spi.max_speed_hz = 1000000
            # Read RC522 version register (0x37) — should return 0x91 or 0x92
            version = spi.xfer2([0x37 << 1 | 0x80, 0x00])[1]
            spi.close()
            if version in (0x91, 0x92, 0x88, 0x12):
                logger.info("RFID: RC522 detected on SPI (version 0x%02x)", version)
                return "rc522", str(spi_device)
            else:
                logger.debug("RFID: SPI device found but no RC522 chip (got 0x%02x)", version)
        except ImportError:
            logger.warning("RFID: SPI device found but spidev module not installed")
        except Exception as e:
            logger.debug("RFID: SPI probe failed: %s", e)
    else:
        logger.debug("RFID: SPI not available (enable with dtparam=spi=on in config.txt)")

    # Check I2C for PN532
    i2c_bus = Path("/dev/i2c-1")
    if i2c_bus.exists():
        try:
            import smbus2
            bus = smbus2.SMBus(1)
            try:
                # PN532 default address
                bus.read_byte(0x24)
                bus.close()
                logger.info("RFID: PN532 detected on I2C")
                return "pn532", str(i2c_bus)
            except OSError:
                bus.close()
        except ImportError:
            logger.warning("RFID: I2C device found but smbus2 module not installed")
    else:
        logger.debug("RFID: I2C not available (enable with dtparam=i2c_arm=on in config.txt)")

    return "none", ""


def detect_audio() -> list[AudioOutput]:
    """Detect available audio outputs."""
    outputs: list[AudioOutput] = []

    # Check ALSA cards
    cards_path = Path("/proc/asound/cards")
    if cards_path.exists():
        try:
            content = cards_path.read_text()
            for line in content.splitlines():
                line = line.strip()
                if not line or line[0].isdigit():
                    match = re.match(r"\s*(\d+)\s+\[(\w+)\s*\]:\s*(.+)", line)
                    if match:
                        card_num = match.group(1)
                        card_id = match.group(2)
                        card_name = match.group(3).strip()

                        if "bcm2835" in card_name.lower():
                            outputs.append(AudioOutput(
                                name="Eingebauter Audio-Ausgang (3.5mm)",
                                type="analog",
                                device=f"hw:{card_num}",
                            ))
                        elif "hdmi" in card_name.lower():
                            outputs.append(AudioOutput(
                                name="HDMI Audio",
                                type="hdmi",
                                device=f"hw:{card_num}",
                            ))
                        elif "hifiberry" in card_id.lower() or "i2s" in card_name.lower():
                            outputs.append(AudioOutput(
                                name=f"I2S DAC ({card_name})",
                                type="i2s",
                                device=f"hw:{card_num}",
                                recommended=True,
                            ))
                        elif "usb" in card_name.lower():
                            outputs.append(AudioOutput(
                                name=f"USB Audio ({card_name})",
                                type="usb",
                                device=f"hw:{card_num}",
                            ))
                        else:
                            outputs.append(AudioOutput(
                                name=card_name,
                                type="unknown",
                                device=f"hw:{card_num}",
                            ))
        except Exception as e:
            logger.warning("Could not detect audio: %s", e)

    # If no I2S DAC found, mark analog as fallback recommendation
    if outputs and not any(a.recommended for a in outputs):
        for a in outputs:
            if a.type == "analog":
                a.recommended = True
                break

    return outputs


def is_gyro_present() -> bool:
    """Check if MPU6050 gyro sensor is connected on I2C."""
    i2c_bus = Path("/dev/i2c-1")
    if not i2c_bus.exists():
        return False

    try:
        import smbus2
        bus = smbus2.SMBus(1)
        try:
            who_am_i = bus.read_byte_data(0x68, 0x75)
            bus.close()
            # MPU6050 WHO_AM_I register should return 0x68
            return who_am_i == 0x68
        except OSError:
            bus.close()
            return False
    except ImportError:
        return False


def detect_gpio() -> bool:
    """Check if GPIO is accessible."""
    return Path("/dev/gpiomem").exists() or Path("/dev/mem").exists()


def detect_all() -> HardwareProfile:
    """Run full hardware detection and return a complete profile."""
    logger.info("Starting hardware detection...")

    pi = detect_pi_model()
    if pi.model == "unknown":
        # Not running on a Pi — return mock profile
        logger.info("Not running on Raspberry Pi, returning mock profile")
        return HardwareProfile(is_mock=True)

    rfid_type, rfid_device = detect_rfid()
    audio = detect_audio()
    gyro = is_gyro_present()
    gpio = detect_gpio()

    profile = HardwareProfile(
        pi=pi,
        rfid_reader=rfid_type,
        rfid_device=rfid_device,
        audio_outputs=audio,
        gyro_detected=gyro,
        gpio_available=gpio,
    )

    logger.info(
        "Hardware detected: %s, RFID=%s, Audio=%d outputs, Gyro=%s, GPIO=%s",
        pi.model, rfid_type, len(audio), gyro, gpio,
    )
    return profile
