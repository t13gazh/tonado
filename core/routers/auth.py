"""Authentication and settings API routes."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.dependencies import (
    get_auth_service,
    get_setup_wizard,
    get_timer_service,
    get_token,
    require_tier,
)
from core.services.auth_service import AuthService, AuthTier
from core.services.setup_wizard import SetupWizard
from core.services.timer_service import TimerService
from core.utils.client_ip import extract_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- Rate limiting ---

# In-memory store: ip -> (failed_attempts, last_attempt_timestamp)
_login_attempts: dict[str, tuple[int, float]] = {}

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60
_CLEANUP_AGE_SECONDS = 600  # Remove entries older than 10 minutes

# Client-IP extraction lives in core.utils.client_ip (shared with rate-limit).


def _cleanup_old_entries() -> None:
    """Remove stale entries older than 10 minutes."""
    now = time.monotonic()
    stale = [ip for ip, (_, ts) in _login_attempts.items() if now - ts > _CLEANUP_AGE_SECONDS]
    for ip in stale:
        del _login_attempts[ip]


def _check_rate_limit(client_ip: str) -> None:
    """Raise 429 if the client is locked out after too many failed attempts."""
    _cleanup_old_entries()
    entry = _login_attempts.get(client_ip)
    if entry is None:
        return
    attempts, last_ts = entry
    if attempts >= _MAX_ATTEMPTS and time.monotonic() - last_ts < _LOCKOUT_SECONDS:
        raise HTTPException(429, "Too many login attempts. Try again later.")


def _record_failure(client_ip: str) -> None:
    """Record a failed login attempt."""
    now = time.monotonic()
    entry = _login_attempts.get(client_ip)
    if entry is None:
        _login_attempts[client_ip] = (1, now)
    else:
        _login_attempts[client_ip] = (entry[0] + 1, now)


def _reset_attempts(client_ip: str) -> None:
    """Clear failed attempts after successful login."""
    _login_attempts.pop(client_ip, None)


# --- Login ---


class LoginRequest(BaseModel):
    pin: str = Field(min_length=4)


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    client_ip = extract_client_ip(request)
    _check_rate_limit(client_ip)

    result = await auth.login(req.pin)
    if result is None:
        _record_failure(client_ip)
        attempts = _login_attempts.get(client_ip, (0, 0))[0]
        logger.warning("Auth failure from %s (attempt %d/%d)", client_ip, attempts, _MAX_ATTEMPTS)
        raise HTTPException(401, "Invalid PIN")

    _reset_attempts(client_ip)
    logger.info("Auth success from %s (tier=%s)", client_ip, result.get("tier", "?"))
    return result


@router.get("/status")
async def auth_status(request: Request, auth: AuthService = Depends(get_auth_service)) -> dict:
    token = get_token(request)
    claims = auth.verify_token(token) if token else None

    return {
        "authenticated": claims is not None,
        "tier": claims.get("tier", "open") if claims else "open",
        "parent_pin_set": await auth.is_pin_set(AuthTier.PARENT),
        "expert_pin_set": await auth.is_pin_set(AuthTier.EXPERT),
    }


# --- PIN management (requires expert or parent tier) ---


class SetPinRequest(BaseModel):
    tier: str = Field(pattern=r"^(parent|expert)$")
    pin: str = Field(min_length=4)


@router.post("/pin")
async def set_pin(
    req: SetPinRequest,
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    wizard: SetupWizard = Depends(get_setup_wizard),
) -> dict:
    target_tier = AuthTier(req.tier)

    # Bootstrap exception: while the setup wizard is still in progress, PINs
    # may be (re-)set without prior auth. Users hit this when they restart
    # the wizard after an earlier aborted run left PINs behind — otherwise
    # they'd be locked out of their own fresh setup and forced to run the
    # expert-guarded /setup/reset path they cannot reach yet.
    setup_in_progress = not wizard.is_complete

    # Setting expert PIN requires expert access (or no expert PIN set yet,
    # or wizard still running)
    if target_tier == AuthTier.EXPERT:
        if await auth.is_pin_set(AuthTier.EXPERT) and not setup_in_progress:
            require_tier(request, AuthTier.EXPERT, auth)
    # Setting parent PIN requires at least parent access (same bootstrap rule)
    elif target_tier == AuthTier.PARENT:
        if await auth.is_pin_set(AuthTier.PARENT) and not setup_in_progress:
            require_tier(request, AuthTier.PARENT, auth)

    await auth.set_pin(target_tier, req.pin)
    return {"status": "ok"}


class RemovePinRequest(BaseModel):
    tier: str = Field(pattern=r"^(parent|expert)$")


@router.delete("/pin")
async def remove_pin(
    req: RemovePinRequest,
    request: Request,
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    target_tier = AuthTier(req.tier)
    require_tier(request, target_tier, auth)
    await auth.remove_pin(target_tier)
    return {"status": "ok"}


# --- Sleep timer ---


class SleepTimerRequest(BaseModel):
    minutes: float = Field(gt=0, le=120)


@router.post("/sleep-timer")
async def start_sleep_timer(
    req: SleepTimerRequest,
    request: Request,
    timer: TimerService = Depends(get_timer_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    await timer.start_sleep_timer(req.minutes)
    return {"status": "ok", "minutes": req.minutes}


@router.delete("/sleep-timer")
async def cancel_sleep_timer(
    request: Request,
    timer: TimerService = Depends(get_timer_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    require_tier(request, AuthTier.PARENT, auth)
    await timer.cancel_sleep_timer()
    return {"status": "ok"}


class SleepTimerExtendRequest(BaseModel):
    minutes: float = Field(gt=0, le=60)


@router.post("/sleep-timer/extend")
async def extend_sleep_timer(
    req: SleepTimerExtendRequest,
    request: Request,
    timer: TimerService = Depends(get_timer_service),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """Extend the running sleep timer by N minutes (typical values 5, 10)."""
    require_tier(request, AuthTier.PARENT, auth)
    try:
        remaining = await timer.extend_sleep_timer(req.minutes)
    except RuntimeError as exc:
        reason = str(exc)
        if reason == "no_active_timer":
            raise HTTPException(409, "Es läuft kein Einschlaftimer")
        if reason == "timer_fading":
            raise HTTPException(409, "Ausblenden hat bereits begonnen")
        raise HTTPException(409, reason)
    return {"status": "ok", "remaining_seconds": remaining}


@router.get("/sleep-timer")
async def sleep_timer_status(timer: TimerService = Depends(get_timer_service)) -> dict:
    return timer.sleep_timer_status()
