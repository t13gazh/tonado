"""Gyroscope hardware abstraction layer for MPU6050.

Based on phonie-gyro logic (https://github.com/t13gazh/phonie-gyro).
Detects gestures: tilt left/right (skip), tilt forward/back (volume), shake (shuffle).
"""

import asyncio
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class Gesture(StrEnum):
    TILT_LEFT = "tilt_left"
    TILT_RIGHT = "tilt_right"
    TILT_FORWARD = "tilt_forward"
    TILT_BACK = "tilt_back"
    SHAKE = "shake"


@dataclass
class AccelData:
    """Raw accelerometer data in g-force units."""

    x: float
    y: float
    z: float


# Sensitivity profiles: (tilt_threshold_degrees, shake_threshold_g)
SENSITIVITY_PROFILES = {
    "gentle": (45.0, 2.5),
    "normal": (30.0, 2.0),
    "wild": (20.0, 1.5),
}


class GyroSensor(ABC):
    """Abstract base class for gyro/accelerometer sensors."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize the sensor hardware."""

    @abstractmethod
    async def stop(self) -> None:
        """Release hardware resources."""

    @abstractmethod
    async def read_accel(self) -> AccelData:
        """Read current accelerometer values."""


class MockGyroSensor(GyroSensor):
    """Mock gyro sensor for development without hardware."""

    def __init__(self) -> None:
        self._accel = AccelData(x=0.0, y=0.0, z=1.0)  # Flat on table

    async def start(self) -> None:
        logger.info("Mock gyro sensor started")

    async def stop(self) -> None:
        logger.info("Mock gyro sensor stopped")

    async def read_accel(self) -> AccelData:
        return self._accel

    def simulate_gesture(self, gesture: Gesture) -> None:
        """Set accelerometer values to simulate a gesture."""
        match gesture:
            case Gesture.TILT_LEFT:
                self._accel = AccelData(x=-0.7, y=0.0, z=0.7)
            case Gesture.TILT_RIGHT:
                self._accel = AccelData(x=0.7, y=0.0, z=0.7)
            case Gesture.TILT_FORWARD:
                self._accel = AccelData(x=0.0, y=0.7, z=0.7)
            case Gesture.TILT_BACK:
                self._accel = AccelData(x=0.0, y=-0.7, z=0.7)
            case Gesture.SHAKE:
                self._accel = AccelData(x=2.5, y=2.5, z=2.5)

    def reset(self) -> None:
        """Reset to flat position."""
        self._accel = AccelData(x=0.0, y=0.0, z=1.0)


class Mpu6050Sensor(GyroSensor):
    """MPU6050 accelerometer/gyroscope via I2C (smbus2)."""

    # MPU6050 registers
    _PWR_MGMT_1 = 0x6B
    _ACCEL_XOUT_H = 0x3B
    _ACCEL_CONFIG = 0x1C

    def __init__(self, bus: int = 1, address: int = 0x68) -> None:
        self._bus_num = bus
        self._address = address
        self._bus = None

    async def start(self) -> None:
        try:
            import smbus2
            self._bus = smbus2.SMBus(self._bus_num)
            # Wake up MPU6050 (clear sleep bit)
            self._bus.write_byte_data(self._address, self._PWR_MGMT_1, 0x00)
            # Set accelerometer range to ±4g
            self._bus.write_byte_data(self._address, self._ACCEL_CONFIG, 0x08)
            logger.info("MPU6050 started on I2C bus %d address 0x%02x", self._bus_num, self._address)
        except ImportError:
            raise RuntimeError("smbus2 not available — install with: pip install smbus2")
        except OSError as e:
            raise RuntimeError(f"Could not initialize MPU6050: {e}")

    async def stop(self) -> None:
        if self._bus:
            self._bus.close()
            self._bus = None

    async def read_accel(self) -> AccelData:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_sync)

    def _read_sync(self) -> AccelData:
        assert self._bus is not None
        data = self._bus.read_i2c_block_data(self._address, self._ACCEL_XOUT_H, 6)
        # Convert to signed 16-bit, then to g-force (±4g range = 8192 LSB/g)
        ax = self._to_signed(data[0] << 8 | data[1]) / 8192.0
        ay = self._to_signed(data[2] << 8 | data[3]) / 8192.0
        az = self._to_signed(data[4] << 8 | data[5]) / 8192.0
        return AccelData(x=ax, y=ay, z=az)

    @staticmethod
    def _to_signed(value: int) -> int:
        return value - 65536 if value > 32767 else value


class GestureDetector:
    """Detects gestures from accelerometer data.

    Uses a simple state machine with debouncing to prevent rapid-fire events.
    """

    def __init__(self, sensitivity: str = "normal") -> None:
        tilt_deg, shake_g = SENSITIVITY_PROFILES.get(sensitivity, SENSITIVITY_PROFILES["normal"])
        self._tilt_threshold = math.sin(math.radians(tilt_deg))
        self._shake_threshold = shake_g
        self._last_gesture: Gesture | None = None
        self._gesture_count = 0
        self._required_readings = 3  # Need N consistent readings before triggering
        self._cooldown_readings = 10  # Readings to skip after a gesture fires

    def detect(self, accel: AccelData) -> Gesture | None:
        """Analyze accelerometer data and return a gesture if detected."""
        if self._cooldown_readings < 10:
            self._cooldown_readings += 1
            return None

        # Check for shake first (high acceleration magnitude)
        magnitude = math.sqrt(accel.x**2 + accel.y**2 + accel.z**2)
        if magnitude > self._shake_threshold:
            return self._confirm(Gesture.SHAKE)

        # Tilt detection based on gravity vector
        gesture = None
        if accel.x < -self._tilt_threshold:
            gesture = Gesture.TILT_LEFT
        elif accel.x > self._tilt_threshold:
            gesture = Gesture.TILT_RIGHT
        elif accel.y > self._tilt_threshold:
            gesture = Gesture.TILT_FORWARD
        elif accel.y < -self._tilt_threshold:
            gesture = Gesture.TILT_BACK

        if gesture is not None:
            return self._confirm(gesture)

        # No gesture — reset
        self._last_gesture = None
        self._gesture_count = 0
        return None

    def _confirm(self, gesture: Gesture) -> Gesture | None:
        """Require consistent readings before confirming a gesture."""
        if gesture == self._last_gesture:
            self._gesture_count += 1
        else:
            self._last_gesture = gesture
            self._gesture_count = 1

        if self._gesture_count >= self._required_readings:
            self._gesture_count = 0
            self._cooldown_readings = 0  # Start cooldown
            return gesture

        return None


def detect_gyro(hardware_mode: str = "auto") -> GyroSensor:
    """Detect and return the appropriate gyro sensor."""
    if hardware_mode == "mock":
        return MockGyroSensor()

    if hardware_mode in ("auto", "pi"):
        try:
            import smbus2  # noqa: F401
            from pathlib import Path
            if Path("/dev/i2c-1").exists():
                # Try to communicate with MPU6050
                bus = smbus2.SMBus(1)
                try:
                    bus.read_byte_data(0x68, 0x75)  # WHO_AM_I register
                    bus.close()
                    logger.info("Auto-detected MPU6050 gyro sensor")
                    return Mpu6050Sensor()
                except OSError:
                    bus.close()
        except ImportError:
            pass

    logger.info("No gyro sensor detected, using mock")
    return MockGyroSensor()
