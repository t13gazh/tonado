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


@dataclass
class AxisMapping:
    """Maps physical sensor axes to logical box axes.

    Each field is (source_axis, sign) where source_axis is "x"/"y"/"z"
    and sign is +1.0 or -1.0.  The default is identity (standard mount).
    """

    tilt_axis: str = "x"
    tilt_sign: float = 1.0
    fwd_axis: str = "y"
    fwd_sign: float = 1.0

    def remap(self, raw: AccelData) -> AccelData:
        """Remap raw sensor data to logical box axes."""
        src = {"x": raw.x, "y": raw.y, "z": raw.z}
        return AccelData(
            x=src[self.tilt_axis] * self.tilt_sign,
            y=src[self.fwd_axis] * self.fwd_sign,
            z=raw.z if self.tilt_axis != "z" and self.fwd_axis != "z" else self._remaining_axis(raw),
        )

    def _remaining_axis(self, raw: AccelData) -> float:
        """Return the value of whichever axis is not used for tilt/fwd."""
        used = {self.tilt_axis, self.fwd_axis}
        src = {"x": raw.x, "y": raw.y, "z": raw.z}
        for axis in ("x", "y", "z"):
            if axis not in used:
                return src[axis]
        return raw.z  # fallback

    def to_dict(self) -> dict:
        return {
            "tilt_axis": self.tilt_axis,
            "tilt_sign": self.tilt_sign,
            "fwd_axis": self.fwd_axis,
            "fwd_sign": self.fwd_sign,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AxisMapping":
        valid_axes = {"x", "y", "z"}
        tilt_axis = data.get("tilt_axis", "x")
        fwd_axis = data.get("fwd_axis", "y")
        if tilt_axis not in valid_axes or fwd_axis not in valid_axes:
            raise ValueError(f"Invalid axes: {tilt_axis}, {fwd_axis}")
        if tilt_axis == fwd_axis:
            raise ValueError("tilt_axis and fwd_axis must differ")
        return cls(
            tilt_axis=tilt_axis,
            tilt_sign=float(data.get("tilt_sign", 1.0)),
            fwd_axis=fwd_axis,
            fwd_sign=float(data.get("fwd_sign", 1.0)),
        )


@dataclass
class AccelBias:
    """Zero-g offset calibration (subtracted from every reading)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def apply(self, raw: AccelData) -> AccelData:
        return AccelData(x=raw.x - self.x, y=raw.y - self.y, z=raw.z - self.z)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, data: dict) -> "AccelBias":
        return cls(x=float(data.get("x", 0)), y=float(data.get("y", 0)), z=float(data.get("z", 0)))


def calibrate_from_readings(
    rest_samples: list[AccelData],
    tilt_samples: list[AccelData],
) -> tuple[AxisMapping, AccelBias]:
    """Calculate axis mapping and bias from rest + tilt-right samples.

    rest_samples: box flat on table (gravity on one axis ≈ 1g)
    tilt_samples: box tilted to the right
    """
    # Average rest readings
    n = len(rest_samples)
    rest_avg = AccelData(
        x=sum(s.x for s in rest_samples) / n,
        y=sum(s.y for s in rest_samples) / n,
        z=sum(s.z for s in rest_samples) / n,
    )

    # Determine gravity axis (highest absolute value at rest)
    axes = {"x": rest_avg.x, "y": rest_avg.y, "z": rest_avg.z}
    grav_axis = max(axes, key=lambda a: abs(axes[a]))
    grav_value = axes[grav_axis]

    # Sanity check: gravity should be close to 1g
    if abs(abs(grav_value) - 1.0) > 0.15:
        raise ValueError(f"Gravity vector invalid: {abs(grav_value):.2f}g (expected ~1.0g)")

    # Bias: expected rest values are 0 on non-gravity axes, ±1g on gravity axis
    expected = {"x": 0.0, "y": 0.0, "z": 0.0}
    expected[grav_axis] = 1.0 if grav_value > 0 else -1.0
    bias = AccelBias(
        x=rest_avg.x - expected["x"],
        y=rest_avg.y - expected["y"],
        z=rest_avg.z - expected["z"],
    )

    # Average tilt readings and apply bias
    m = len(tilt_samples)
    tilt_avg = AccelData(
        x=sum(s.x for s in tilt_samples) / m - bias.x,
        y=sum(s.y for s in tilt_samples) / m - bias.y,
        z=sum(s.z for s in tilt_samples) / m - bias.z,
    )

    # Delta from expected rest position (bias-corrected)
    delta = {
        "x": tilt_avg.x - expected["x"],
        "y": tilt_avg.y - expected["y"],
        "z": tilt_avg.z - expected["z"],
    }

    # Remove gravity axis from candidates — tilt axis is non-gravity
    non_grav = {a: v for a, v in delta.items() if a != grav_axis}
    tilt_axis = max(non_grav, key=lambda a: abs(non_grav[a]))
    tilt_sign = 1.0 if non_grav[tilt_axis] > 0 else -1.0

    # Forward axis is the remaining non-gravity axis
    remaining = [a for a in ("x", "y", "z") if a != grav_axis and a != tilt_axis]
    fwd_axis = remaining[0]

    # Forward sign via right-hand rule: forward = cross(up, right)
    # For axis triplets, sign follows from cyclic order (xyz, yzx, zxy = +1)
    axis_order = {"x": 0, "y": 1, "z": 2}
    grav_sign = 1.0 if grav_value > 0 else -1.0
    cross_sign = 1.0 if (axis_order[grav_axis] + 1) % 3 == axis_order[tilt_axis] else -1.0
    fwd_sign = cross_sign * grav_sign * tilt_sign

    mapping = AxisMapping(
        tilt_axis=tilt_axis,
        tilt_sign=tilt_sign,
        fwd_axis=fwd_axis,
        fwd_sign=fwd_sign,
    )

    logger.info(
        "Calibration: gravity=%s (%.2fg), tilt=%s%s, fwd=%s%s",
        grav_axis, grav_value,
        "+" if tilt_sign > 0 else "-", tilt_axis,
        "+" if fwd_sign > 0 else "-", fwd_axis,
    )

    return mapping, bias


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
        loop = asyncio.get_running_loop()
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

    _HISTORY_SIZE = 10  # Ring buffer size (0.5s at 20Hz)

    def __init__(self, sensitivity: str = "normal") -> None:
        tilt_deg, shake_g = SENSITIVITY_PROFILES.get(sensitivity, SENSITIVITY_PROFILES["normal"])
        self._tilt_threshold = math.sin(math.radians(tilt_deg))
        self._shake_amplitude = 0.8  # Peak amplitude threshold for shake
        self._shake_flips_required = 3  # Min sign flips in any axis
        self._tilt_jitter_limit = 0.3  # Variance above which tilt is suppressed
        self._last_gesture: Gesture | None = None
        self._gesture_count = 0
        self._required_readings = 3
        self._cooldown_readings = 10
        # Ring buffers for sign-flip shake detection
        self._x_buf: list[float] = []
        self._y_buf: list[float] = []

    @staticmethod
    def _count_sign_flips(buf: list[float]) -> int:
        flips = 0
        for i in range(1, len(buf)):
            if buf[i] * buf[i - 1] < 0:
                flips += 1
        return flips

    @staticmethod
    def _variance(buf: list[float]) -> float:
        if len(buf) < 2:
            return 0.0
        mean = sum(buf) / len(buf)
        return sum((v - mean) ** 2 for v in buf) / len(buf)

    def detect(self, accel: AccelData) -> Gesture | None:
        """Analyze accelerometer data and return a gesture if detected."""
        if self._cooldown_readings < 10:
            self._cooldown_readings += 1
            # Still collect history during cooldown for shake detection
            self._x_buf.append(accel.x)
            self._y_buf.append(accel.y)
            if len(self._x_buf) > self._HISTORY_SIZE:
                self._x_buf.pop(0)
                self._y_buf.pop(0)
            return None

        # Update ring buffers
        self._x_buf.append(accel.x)
        self._y_buf.append(accel.y)
        if len(self._x_buf) > self._HISTORY_SIZE:
            self._x_buf.pop(0)
            self._y_buf.pop(0)

        # --- Shake detection (sign-flip frequency) ---
        # Shake = rapid oscillation = multiple sign flips + significant amplitude
        if len(self._x_buf) >= 6:
            x_flips = self._count_sign_flips(self._x_buf)
            y_flips = self._count_sign_flips(self._y_buf)
            max_flips = max(x_flips, y_flips)
            peak = max(
                max((abs(v) for v in self._x_buf), default=0),
                max((abs(v) for v in self._y_buf), default=0),
            )
            if max_flips >= self._shake_flips_required and peak > self._shake_amplitude:
                self._x_buf.clear()
                self._y_buf.clear()
                self._last_gesture = None
                self._gesture_count = 0
                self._cooldown_readings = 0
                return Gesture.SHAKE

        # --- Tilt detection (with jitter guard) ---
        # Suppress tilt if axis is oscillating (shake residual)
        x_jittery = self._variance(self._x_buf[-6:]) > self._tilt_jitter_limit
        y_jittery = self._variance(self._y_buf[-6:]) > self._tilt_jitter_limit

        gesture = None
        if not x_jittery:
            if accel.x < -self._tilt_threshold:
                gesture = Gesture.TILT_LEFT
            elif accel.x > self._tilt_threshold:
                gesture = Gesture.TILT_RIGHT
        if gesture is None and not y_jittery:
            if accel.y > self._tilt_threshold:
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
            self._cooldown_readings = 0
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
