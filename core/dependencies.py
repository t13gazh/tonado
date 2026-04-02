"""Shared FastAPI dependencies for authentication and service injection."""

from fastapi import HTTPException, Request

from core.services.auth_service import AuthService, AuthTier
from core.services.backup_service import BackupService
from core.services.button_service import ButtonService
from core.services.captive_portal import CaptivePortalService
from core.services.card_service import CardService
from core.services.config_service import ConfigService
from core.services.gyro_service import GyroService
from core.services.hardware_detector import HardwareDetector
from core.services.library_service import LibraryService
from core.services.player_service import PlayerService
from core.services.playlist_service import PlaylistService
from core.services.setup_wizard import SetupWizard
from core.services.stream_service import StreamService
from core.services.system_service import SystemService
from core.services.timer_service import TimerService
from core.services.wifi_service import WifiService
from core.settings import Settings


# --- Auth helpers ---


def get_token(request: Request) -> str | None:
    """Extract JWT token from Authorization header."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def require_tier(request: Request, tier: AuthTier, auth: AuthService | None) -> None:
    """Raise 403 if token doesn't grant access to the required tier.

    If auth is None (e.g. during first setup), access is allowed.
    """
    if auth is None:
        return
    token = get_token(request)
    if not auth.check_access(token, tier):
        raise HTTPException(403, "Access denied")


# --- Service dependencies ---
# Each returns the service stored on app.state during lifespan startup.


def get_player(request: Request) -> PlayerService:
    return request.app.state.player_service


def get_card_service(request: Request) -> CardService:
    return request.app.state.card_service


def get_config_service(request: Request) -> ConfigService:
    return request.app.state.config_service


def get_library_service(request: Request) -> LibraryService:
    return request.app.state.library_service


def get_stream_service(request: Request) -> StreamService:
    return request.app.state.stream_service


def get_playlist_service(request: Request) -> PlaylistService:
    return request.app.state.playlist_service


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_timer_service(request: Request) -> TimerService:
    return request.app.state.timer_service


def get_system_service(request: Request) -> SystemService:
    return request.app.state.system_service


def get_backup_service(request: Request) -> BackupService:
    return request.app.state.backup_service


def get_setup_wizard(request: Request) -> SetupWizard:
    return request.app.state.setup_wizard


def get_wifi_service(request: Request) -> WifiService:
    return request.app.state.wifi_service


def get_captive_portal(request: Request) -> CaptivePortalService:
    return request.app.state.captive_portal


def get_gyro_service(request: Request) -> GyroService:
    return request.app.state.gyro_service


def get_hardware_detector(request: Request) -> HardwareDetector:
    return request.app.state.hardware_detector


def get_button_service(request: Request) -> ButtonService:
    return request.app.state.button_service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
