"""Application settings loaded from environment / .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Paths
    data_dir: Path = Path.home() / "tonado"
    media_dir: Path = Path.home() / "tonado" / "media"
    db_path: Path = Path("/opt/tonado/config/tonado.db")

    # MPD
    mpd_host: str = "localhost"
    mpd_port: int = 6600

    # Hardware mode: "auto", "mock", "pi"
    hardware_mode: str = "auto"

    # Card behavior
    card_rescan_cooldown: float = 2.0
    card_remove_pauses: bool = False

    # Gyro
    gyro_enabled: bool = True
    gyro_sensitivity: str = "normal"  # "gentle", "normal", "wild"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080

    model_config = {"env_prefix": "TONADO_", "env_file": ".env"}
