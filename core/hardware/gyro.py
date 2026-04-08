"""Gyroscope hardware abstraction layer for MPU6050.

Based on phonie-gyro logic (https://github.com/t13gazh/phonie-gyro).
Detects gestures: tilt left/right (skip), tilt forward/back (play/stop), shake (shuffle).
"""

import asyncio
import logging
import math
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
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
        used = {self.tilt_axis, self.fwd_axis}
        remaining = [a for a in ("x", "y", "z") if a not in used]
        return AccelData(
            x=src[self.tilt_axis] * self.tilt_sign,
            y=src[self.fwd_axis] * self.fwd_sign,
            z=src[remaining[0]] if remaining else raw.z,
        )

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
    """Calculate axis mapping and bias from rest + tilt-right samples."""
    n = len(rest_samples)
    rest_avg = AccelData(
        x=sum(s.x for s in rest_samples) / n,
        y=sum(s.y for s in rest_samples) / n,
        z=sum(s.z for s in rest_samples) / n,
    )

    axes = {"x": rest_avg.x, "y": rest_avg.y, "z": rest_avg.z}
    grav_axis = max(axes, key=lambda a: abs(axes[a]))
    grav_value = axes[grav_axis]

    if abs(abs(grav_value) - 1.0) > 0.15:
        raise ValueError(f"Gravity vector invalid: {abs(grav_value):.2f}g (expected ~1.0g)")

    expected = {"x": 0.0, "y": 0.0, "z": 0.0}
    expected[grav_axis] = 1.0 if grav_value > 0 else -1.0
    bias = AccelBias(
        x=rest_avg.x - expected["x"],
        y=rest_avg.y - expected["y"],
        z=rest_avg.z - expected["z"],
    )

    m = len(tilt_samples)
    tilt_avg = AccelData(
        x=sum(s.x for s in tilt_samples) / m - bias.x,
        y=sum(s.y for s in tilt_samples) / m - bias.y,
        z=sum(s.z for s in tilt_samples) / m - bias.z,
    )

    delta = {a: getattr(tilt_avg, a) - expected[a] for a in ("x", "y", "z")}
    non_grav = {a: v for a, v in delta.items() if a != grav_axis}
    tilt_axis = max(non_grav, key=lambda a: abs(non_grav[a]))
    tilt_sign = 1.0 if non_grav[tilt_axis] > 0 else -1.0

    remaining = [a for a in ("x", "y", "z") if a != grav_axis and a != tilt_axis]
    fwd_axis = remaining[0]

    axis_order = {"x": 0, "y": 1, "z": 2}
    grav_sign = 1.0 if grav_value > 0 else -1.0
    cross_sign = 1.0 if (axis_order[grav_axis] + 1) % 3 == axis_order[tilt_axis] else -1.0
    fwd_sign = cross_sign * grav_sign * tilt_sign

    mapping = AxisMapping(tilt_axis=tilt_axis, tilt_sign=tilt_sign, fwd_axis=fwd_axis, fwd_sign=fwd_sign)
    logger.info(
        "Calibration: gravity=%s (%.2fg), tilt=%s%s, fwd=%s%s",
        grav_axis, grav_value,
        "+" if tilt_sign > 0 else "-", tilt_axis,
        "+" if fwd_sign > 0 else "-", fwd_axis,
    )
    return mapping, bias


# --- Sensor hardware ---


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
        self._accel = AccelData(x=0.0, y=0.0, z=1.0)

    async def start(self) -> None:
        logger.info("Mock gyro sensor started")

    async def stop(self) -> None:
        logger.info("Mock gyro sensor stopped")

    async def read_accel(self) -> AccelData:
        return self._accel

    def simulate_gesture(self, gesture: Gesture) -> None:
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
        self._accel = AccelData(x=0.0, y=0.0, z=1.0)


class Mpu6050Sensor(GyroSensor):
    """MPU6050 accelerometer/gyroscope via I2C (smbus2).

    Ported from phonie-gyro: ±2g range, DLPF filter, dedicated thread executor.
    """

    _PWR_MGMT_1 = 0x6B
    _SMPLRT_DIV = 0x19
    _CONFIG = 0x1A
    _ACCEL_XOUT_H = 0x3B
    _ACCEL_CONFIG = 0x1C
    _ACCEL_SENS = 16384.0  # ±2g range

    def __init__(self, bus: int = 1, address: int = 0x68) -> None:
        self._bus_num = bus
        self._address = address
        self._bus = None
        # Dedicated single-thread executor to avoid blocking the event loop
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gyro-i2c")

    async def start(self) -> None:
        try:
            import smbus2
            self._bus = smbus2.SMBus(self._bus_num)
            # Wake up
            self._bus.write_byte_data(self._address, self._PWR_MGMT_1, 0x00)
            # Sample rate divider: 1kHz / (7+1) = 125 Hz internal
            self._bus.write_byte_data(self._address, self._SMPLRT_DIV, 0x07)
            # DLPF: ~94 Hz bandwidth (smooths high-frequency noise)
            self._bus.write_byte_data(self._address, self._CONFIG, 0x02)
            # ±2g range (double resolution vs ±4g)
            self._bus.write_byte_data(self._address, self._ACCEL_CONFIG, 0x00)
            logger.info("MPU6050 started: ±2g, DLPF=94Hz, bus %d addr 0x%02x", self._bus_num, self._address)
        except ImportError:
            raise RuntimeError("smbus2 not available — install with: pip install smbus2")
        except OSError as e:
            raise RuntimeError(f"Could not initialize MPU6050: {e}")

    async def stop(self) -> None:
        if self._bus:
            self._bus.close()
            self._bus = None
        self._executor.shutdown(wait=False)

    async def read_accel(self) -> AccelData:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._read_sync)

    def _read_sync(self) -> AccelData:
        assert self._bus is not None
        data = self._bus.read_i2c_block_data(self._address, self._ACCEL_XOUT_H, 6)
        ax = self._to_signed(data[0] << 8 | data[1]) / self._ACCEL_SENS
        ay = self._to_signed(data[2] << 8 | data[3]) / self._ACCEL_SENS
        az = self._to_signed(data[4] << 8 | data[5]) / self._ACCEL_SENS
        return AccelData(x=ax, y=ay, z=az)

    @staticmethod
    def _to_signed(value: int) -> int:
        return value - 65536 if value > 32767 else value


# --- Gesture detection (ported from phonie-gyro) ---

# Sensitivity profiles: (roll_trigger_deg, pitch_trigger_deg, axis_margin_deg, dwell_ms)
SENSITIVITY_PROFILES = {
    "gentle": (18, 20, 10, 400),
    "normal": (14, 16, 8, 300),
    "wild": (10, 12, 6, 200),
}


def _dot(a: tuple, b: tuple) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: tuple, b: tuple) -> tuple:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v: tuple) -> tuple:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-9:
        return (0.0, 0.0, 1.0)
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _angle_about_axis(axis: tuple, g0: tuple, g: tuple) -> float:
    """Signed angle between g0 and g, projected onto rotation around axis."""
    c = _cross(g0, g)
    num = _dot(axis, c)
    den = max(-1.0, min(1.0, _dot(g0, g)))
    return math.degrees(math.atan2(num, den))


class GestureDetector:
    """Detects gestures from filtered accelerometer data.

    Ported from phonie-gyro: EMA filter, angle-based detection relative
    to base gravity, dwell timers, neutral-zone re-arm.
    """

    # EMA filter coefficient (0.16 = strong smoothing, matches phonie-gyro)
    ALPHA = 0.16
    # Plausibility: gravity magnitude must be in this range
    G_MIN = 0.7
    G_MAX = 1.3
    # Neutral zone: both angles must be below this (degrees)
    NEUTRAL_DEG = 10.0
    NEUTRAL_DWELL_MS = 700.0
    # Debounce between gestures
    DEBOUNCE_MS = 900.0
    # Shake: consecutive implausible readings
    SHAKE_COUNT = 4
    SHAKE_WINDOW = 8

    def __init__(self, sensitivity: str = "normal") -> None:
        profile = SENSITIVITY_PROFILES.get(sensitivity, SENSITIVITY_PROFILES["normal"])
        self._roll_trig = float(profile[0])
        self._pitch_trig = float(profile[1])
        self._axis_margin = float(profile[2])
        self._dwell_ms = float(profile[3])

        # Filtered accelerometer values
        self._fx = 0.0
        self._fy = 0.0
        self._fz = 1.0
        self._initialized = False

        # Base gravity vector (set during re-arm)
        self._base_g: tuple = (0.0, 0.0, 1.0)

        # State machine
        self._armed = False
        self._warmup_until = 0.0  # ms timestamp

        # Dwell timers (ms timestamp when angle first exceeded threshold)
        self._roll_pos_since = 0.0
        self._roll_neg_since = 0.0
        self._pitch_pos_since = 0.0
        self._pitch_neg_since = 0.0

        # Neutral zone timer
        self._neutral_since = 0.0

        # Debounce
        self._last_action_time = 0.0

        # Shake detection
        self._implausible_count = 0
        self._implausible_window = 0

    def reset_base(self, accel: AccelData | None = None) -> None:
        """Set the base gravity vector (rest position)."""
        if accel:
            self._base_g = _norm((accel.x, accel.y, accel.z))
            self._fx = accel.x
            self._fy = accel.y
            self._fz = accel.z
            self._initialized = True
        self._armed = True
        self._warmup_until = time.monotonic() * 1000 + 2000
        self._neutral_since = 0.0
        self._roll_pos_since = 0.0
        self._roll_neg_since = 0.0
        self._pitch_pos_since = 0.0
        self._pitch_neg_since = 0.0
        self._implausible_count = 0

    def detect(self, accel: AccelData) -> Gesture | None:
        """Process one accelerometer reading and return a gesture or None."""
        now = time.monotonic() * 1000  # ms

        # Initialize filter on first reading
        if not self._initialized:
            self._fx, self._fy, self._fz = accel.x, accel.y, accel.z
            self._base_g = _norm((accel.x, accel.y, accel.z))
            self._initialized = True
            self._armed = True
            self._warmup_until = now + 2000
            return None

        # EMA low-pass filter
        a = self.ALPHA
        self._fx = a * accel.x + (1 - a) * self._fx
        self._fy = a * accel.y + (1 - a) * self._fy
        self._fz = a * accel.z + (1 - a) * self._fz

        # Shake detection uses RAW magnitude (unfiltered) — the EMA filter
        # dampens peaks so heavily that filtered magnitude never exceeds 1.3g
        raw_mag = math.sqrt(accel.x ** 2 + accel.y ** 2 + accel.z ** 2)
        if raw_mag < self.G_MIN or raw_mag > self.G_MAX:
            # Implausible reading — might be shaking
            self._implausible_window += 1
            self._implausible_count += 1
            if self._implausible_count >= self.SHAKE_COUNT:
                self._implausible_count = 0
                self._implausible_window = 0
                if now - self._last_action_time >= self.DEBOUNCE_MS:
                    self._last_action_time = now
                    self._armed = False
                    return Gesture.SHAKE
            if self._implausible_window > self.SHAKE_WINDOW:
                self._implausible_count = 0
                self._implausible_window = 0
            return None

        # Reset shake counter on plausible reading
        if self._implausible_window > 0:
            self._implausible_window += 1
            if self._implausible_window > self.SHAKE_WINDOW:
                self._implausible_count = 0
                self._implausible_window = 0

        # Warmup period — no gestures
        if now < self._warmup_until:
            return None

        # Compute angles relative to base gravity
        g = _norm((self._fx, self._fy, self._fz))
        dr = _angle_about_axis((0, 1, 0), self._base_g, g)  # Roll (left/right)
        dp = _angle_about_axis((1, 0, 0), self._base_g, g)  # Pitch (fwd/back)

        abs_r = abs(dr)
        abs_p = abs(dp)

        # --- Re-arm logic: must return to neutral zone ---
        if not self._armed:
            if abs_r < self.NEUTRAL_DEG and abs_p < self.NEUTRAL_DEG:
                if self._neutral_since == 0:
                    self._neutral_since = now
                elif now - self._neutral_since >= self.NEUTRAL_DWELL_MS:
                    # Re-arm with new base gravity
                    self._base_g = _norm((self._fx, self._fy, self._fz))
                    self._armed = True
                    self._neutral_since = 0.0
                    self._roll_pos_since = 0.0
                    self._roll_neg_since = 0.0
                    self._pitch_pos_since = 0.0
                    self._pitch_neg_since = 0.0
            else:
                self._neutral_since = 0.0
            return None

        # Debounce
        if now - self._last_action_time < self.DEBOUNCE_MS:
            return None

        # --- Gesture detection with dwell timer ---
        # Determine dominant axis (must be clearly dominant)
        gesture = None

        if abs_r >= self._roll_trig and (abs_r - abs_p) >= self._axis_margin:
            # Roll dominant
            if dr > 0:
                if self._roll_pos_since == 0:
                    self._roll_pos_since = now
                elif now - self._roll_pos_since >= self._dwell_ms:
                    gesture = Gesture.TILT_RIGHT
            else:
                if self._roll_neg_since == 0:
                    self._roll_neg_since = now
                elif now - self._roll_neg_since >= self._dwell_ms:
                    gesture = Gesture.TILT_LEFT
            # Reset pitch timers
            self._pitch_pos_since = 0.0
            self._pitch_neg_since = 0.0

        elif abs_p >= self._pitch_trig and (abs_p - abs_r) >= self._axis_margin:
            # Pitch dominant
            if dp > 0:
                if self._pitch_pos_since == 0:
                    self._pitch_pos_since = now
                elif now - self._pitch_pos_since >= self._dwell_ms:
                    gesture = Gesture.TILT_FORWARD
            else:
                if self._pitch_neg_since == 0:
                    self._pitch_neg_since = now
                elif now - self._pitch_neg_since >= self._dwell_ms:
                    gesture = Gesture.TILT_BACK
            # Reset roll timers
            self._roll_pos_since = 0.0
            self._roll_neg_since = 0.0

        else:
            # No dominant axis — reset all timers
            self._roll_pos_since = 0.0
            self._roll_neg_since = 0.0
            self._pitch_pos_since = 0.0
            self._pitch_neg_since = 0.0

        if gesture is not None:
            self._last_action_time = now
            self._armed = False  # Must re-arm through neutral zone
            logger.debug("Gesture: %s (roll=%.1f° pitch=%.1f°)", gesture, dr, dp)
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
                bus = smbus2.SMBus(1)
                try:
                    bus.read_byte_data(0x68, 0x75)
                    bus.close()
                    logger.info("Auto-detected MPU6050 gyro sensor")
                    return Mpu6050Sensor()
                except OSError:
                    bus.close()
        except ImportError:
            pass

    logger.info("No gyro sensor detected, using mock")
    return MockGyroSensor()
