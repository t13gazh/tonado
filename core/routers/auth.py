"""Authentication and settings API routes."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.services.auth_service import AuthService, AuthTier
from core.services.timer_service import TimerService

router = APIRouter(prefix="/api/auth", tags=["auth"])

_auth: AuthService | None = None
_timer: TimerService | None = None


def init(auth_service: AuthService, timer_service: TimerService) -> None:
    global _auth, _timer
    _auth = auth_service
    _timer = timer_service


def _get_auth() -> AuthService:
    if _auth is None:
        raise HTTPException(503, "Auth service not available")
    return _auth


def _get_timer() -> TimerService:
    if _timer is None:
        raise HTTPException(503, "Timer service not available")
    return _timer


def _get_token(request: Request) -> str | None:
    """Extract JWT token from Authorization header."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def _require_tier(request: Request, tier: AuthTier) -> None:
    """Raise 401/403 if token doesn't grant access to the required tier."""
    auth = _get_auth()
    token = _get_token(request)
    if not auth.check_access(token, tier):
        raise HTTPException(403, "Zugriff verweigert")


# --- Login ---


class LoginRequest(BaseModel):
    pin: str = Field(min_length=4)


@router.post("/login")
async def login(req: LoginRequest) -> dict:
    result = await _get_auth().login(req.pin)
    if result is None:
        raise HTTPException(401, "Ungültige PIN")
    return result


@router.get("/status")
async def auth_status(request: Request) -> dict:
    auth = _get_auth()
    token = _get_token(request)
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
async def set_pin(req: SetPinRequest, request: Request) -> dict:
    auth = _get_auth()
    target_tier = AuthTier(req.tier)

    # Setting expert PIN requires expert access (or no expert PIN set yet)
    if target_tier == AuthTier.EXPERT:
        if await auth.is_pin_set(AuthTier.EXPERT):
            _require_tier(request, AuthTier.EXPERT)
    # Setting parent PIN requires at least parent access
    elif target_tier == AuthTier.PARENT:
        if await auth.is_pin_set(AuthTier.PARENT):
            _require_tier(request, AuthTier.PARENT)

    await auth.set_pin(target_tier, req.pin)
    return {"status": "ok"}


class RemovePinRequest(BaseModel):
    tier: str = Field(pattern=r"^(parent|expert)$")


@router.delete("/pin")
async def remove_pin(req: RemovePinRequest, request: Request) -> dict:
    target_tier = AuthTier(req.tier)
    _require_tier(request, target_tier)
    await _get_auth().remove_pin(target_tier)
    return {"status": "ok"}


# --- Sleep timer ---


class SleepTimerRequest(BaseModel):
    minutes: float = Field(gt=0, le=120)


@router.post("/sleep-timer")
async def start_sleep_timer(req: SleepTimerRequest) -> dict:
    await _get_timer().start_sleep_timer(req.minutes)
    return {"status": "ok", "minutes": req.minutes}


@router.delete("/sleep-timer")
async def cancel_sleep_timer() -> dict:
    await _get_timer().cancel_sleep_timer()
    return {"status": "ok"}


@router.get("/sleep-timer")
async def sleep_timer_status() -> dict:
    return _get_timer().sleep_timer_status()
