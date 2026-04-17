"""PIN-based authentication service with JWT tokens.

Three access tiers:
- open: Player view, no PIN needed
- parent: Library, cards, uploads, settings — PIN protected
- expert: Hardware, system, WiFi, debug — separate PIN
"""

import hashlib
import hmac
import logging
import secrets
import time
from enum import StrEnum
from typing import Any

import jwt

from core.services.base import BaseService
from core.services.config_service import ConfigService

logger = logging.getLogger(__name__)

# JWT settings
_JWT_ALGORITHM = "HS256"
# Short enough that a stolen token from a lost phone expires within one
# evening, long enough to cover a parent's normal usage session.
_JWT_EXPIRE_HOURS = 4
_JWT_ISSUER = "tonado"
_JWT_AUDIENCE = "tonado-api"


class AuthTier(StrEnum):
    OPEN = "open"
    PARENT = "parent"
    EXPERT = "expert"


# Tier hierarchy: expert > parent > open
_TIER_LEVELS = {AuthTier.OPEN: 0, AuthTier.PARENT: 1, AuthTier.EXPERT: 2}


class AuthService(BaseService):
    """Manages PIN-based authentication with JWT tokens."""

    def __init__(self, config: ConfigService) -> None:
        super().__init__()
        self._config = config
        self._jwt_secret: str = ""
        self._pin_cache: dict[str, bool] = {}
        self._setup_complete: bool = False

    async def start(self) -> None:
        """Initialize auth service. Generate JWT secret if not set."""
        secret = await self._config.get("auth.jwt_secret")
        if not secret:
            secret = secrets.token_hex(32)
            await self._config.set("auth.jwt_secret", secret)
        self._jwt_secret = secret
        # Cache PIN status for sync access checks
        for tier in (AuthTier.PARENT, AuthTier.EXPERT):
            self._pin_cache[tier.value] = await self.is_pin_set(tier)
        # Cache setup completion state (locks down the LAN once wizard is done)
        saved_step = await self._config.get("setup.step")
        self._setup_complete = saved_step == "completed"
        logger.info("Auth service started")

    def set_setup_complete(self, complete: bool) -> None:
        """Update the cached setup-complete flag (called by SetupWizard)."""
        self._setup_complete = complete

    async def is_pin_set(self, tier: AuthTier) -> bool:
        """Check if a PIN is configured for a tier."""
        pin_hash = await self._config.get(f"auth.pin_hash.{tier}")
        return pin_hash is not None and pin_hash != ""

    async def set_pin(self, tier: AuthTier, pin: str) -> None:
        """Set or update the PIN for a tier.

        Rotates the JWT secret so any tokens issued before the PIN change
        are immediately invalidated — the usual reason to change a PIN is
        a suspected compromise.
        """
        if len(pin) < 4:
            raise ValueError("PIN muss mindestens 4 Zeichen lang sein")
        salt = secrets.token_hex(16)
        derived = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
        pin_hash = f"{salt}${derived}"
        await self._config.set(f"auth.pin_hash.{tier}", pin_hash)
        self._pin_cache[tier.value] = True
        await self._rotate_jwt_secret()
        logger.info("PIN set for tier: %s", tier)

    async def _rotate_jwt_secret(self) -> None:
        """Generate a fresh JWT signing secret and invalidate every existing token."""
        new_secret = secrets.token_hex(32)
        await self._config.set("auth.jwt_secret", new_secret)
        self._jwt_secret = new_secret
        logger.info("JWT secret rotated — existing tokens invalidated")

    async def remove_pin(self, tier: AuthTier) -> None:
        """Remove the PIN for a tier (makes it unprotected)."""
        await self._config.delete(f"auth.pin_hash.{tier}")
        self._pin_cache[tier.value] = False
        logger.info("PIN removed for tier: %s", tier)

    async def verify_pin(self, tier: AuthTier, pin: str) -> bool:
        """Verify a PIN against the stored hash."""
        pin_hash = await self._config.get(f"auth.pin_hash.{tier}")
        if not pin_hash:
            return True  # No PIN set = always pass
        if "$" not in pin_hash:
            return False
        salt, stored_hash = pin_hash.split("$", 1)
        derived = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
        return hmac.compare_digest(derived, stored_hash)

    async def login(self, pin: str) -> dict[str, Any] | None:
        """Attempt login with a PIN. Returns JWT token and tier on success.

        Tries expert first, then parent. Returns the highest matching tier.
        """
        # Try expert PIN
        if await self.is_pin_set(AuthTier.EXPERT):
            if await self.verify_pin(AuthTier.EXPERT, pin):
                token = self._create_token(AuthTier.EXPERT)
                return {"token": token, "tier": AuthTier.EXPERT.value}

        # Try parent PIN
        if await self.is_pin_set(AuthTier.PARENT):
            if await self.verify_pin(AuthTier.PARENT, pin):
                token = self._create_token(AuthTier.PARENT)
                return {"token": token, "tier": AuthTier.PARENT.value}

        return None

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify a JWT token and return its claims (including iss/aud)."""
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[_JWT_ALGORITHM],
                issuer=_JWT_ISSUER,
                audience=_JWT_AUDIENCE,
            )
            return payload
        except jwt.InvalidTokenError:
            return None

    def check_access(self, token: str | None, required_tier: AuthTier) -> bool:
        """Check if a token grants access to the required tier.

        Open tier always passes. Parent/Expert tiers need valid tokens.
        Expert token also grants parent access.
        Before setup is completed, missing PINs allow access (bootstrap phase).
        After setup is completed, missing PINs lock down the tier (sealed).
        """
        if required_tier == AuthTier.OPEN:
            return True

        # Bootstrap phase: allow access when no PIN is set yet so the
        # initial setup flow (and wizard reset) remains usable.
        # After setup completion the wizard guarantees a parent PIN,
        # so an unset PIN must NOT grant access anymore.
        if not self._pin_cache.get(required_tier.value, False):
            return not self._setup_complete

        if not token:
            return False

        claims = self.verify_token(token)
        if not claims:
            return False

        token_tier = claims.get("tier", "open")
        token_level = _TIER_LEVELS.get(AuthTier(token_tier), 0)
        required_level = _TIER_LEVELS.get(required_tier, 0)

        return token_level >= required_level

    def _create_token(self, tier: AuthTier) -> str:
        """Create a JWT token for a tier with iss/aud claims."""
        payload = {
            "tier": tier.value,
            "iat": int(time.time()),
            "exp": int(time.time()) + _JWT_EXPIRE_HOURS * 3600,
            "iss": _JWT_ISSUER,
            "aud": _JWT_AUDIENCE,
        }
        return jwt.encode(payload, self._jwt_secret, algorithm=_JWT_ALGORITHM)
