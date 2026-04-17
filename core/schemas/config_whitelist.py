"""Whitelist of config keys that can be written via the public API.

Restricts PUT /api/config to a known set of keys with type and range
validation. Internal callers (setup wizard, backup restore, service-
owned housekeeping) continue to use ConfigService.set() directly and
are not affected by this whitelist.
"""

from typing import Any, Callable


def _bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise ValueError("expected boolean")
    return v


def _int_range(lo: int, hi: int) -> Callable[[Any], int]:
    def check(v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("expected integer")
        if not lo <= v <= hi:
            raise ValueError(f"expected integer in [{lo}, {hi}]")
        return v
    return check


def _number_range(lo: float, hi: float) -> Callable[[Any], float]:
    def check(v: Any) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("expected number")
        f = float(v)
        if not lo <= f <= hi:
            raise ValueError(f"expected number in [{lo}, {hi}]")
        return f
    return check


def _enum(*opts: str) -> Callable[[Any], str]:
    def check(v: Any) -> str:
        if not isinstance(v, str) or v not in opts:
            raise ValueError(f"expected one of {opts}")
        return v
    return check


PUBLIC_CONFIG_WHITELIST: dict[str, Callable[[Any], Any]] = {
    "player.max_volume": _int_range(10, 100),
    "player.startup_volume": _int_range(0, 100),
    "card.remove_pauses": _bool,
    "card.rescan_cooldown": _number_range(0.5, 30.0),
    "gyro.enabled": _bool,
    "gyro.sensitivity": _enum("sanft", "normal", "wild"),
    "system.idle_shutdown_minutes": _int_range(0, 1440),
    "sleep_fade_duration": _int_range(0, 300),
    "wizard.expert_mode": _bool,
}


def validate_public_config(key: str, value: Any) -> Any:
    """Validate a public config write and return the normalised value.

    Raises ValueError if the key is not writeable via the public API or
    the value does not match the type/range constraint for that key.
    """
    validator = PUBLIC_CONFIG_WHITELIST.get(key)
    if validator is None:
        raise ValueError(f"config key '{key}' is not writeable via API")
    return validator(value)
