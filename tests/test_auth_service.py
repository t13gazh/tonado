"""Tests for the auth service."""

from pathlib import Path

import pytest

import time

from core.services.auth_service import AuthService, AuthTier, _JWT_EXPIRE_HOURS
from core.services.config_service import ConfigService


@pytest.fixture
async def auth_service(config_service: ConfigService) -> AuthService:
    service = AuthService(config_service)
    await service.start()
    return service


@pytest.mark.asyncio
async def test_no_pin_by_default(auth_service: AuthService) -> None:
    assert not await auth_service.is_pin_set(AuthTier.PARENT)
    assert not await auth_service.is_pin_set(AuthTier.EXPERT)


@pytest.mark.asyncio
async def test_set_and_verify_pin(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    assert await auth_service.is_pin_set(AuthTier.PARENT)
    assert await auth_service.verify_pin(AuthTier.PARENT, "1234")
    assert not await auth_service.verify_pin(AuthTier.PARENT, "wrong")


@pytest.mark.asyncio
async def test_remove_pin(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    await auth_service.remove_pin(AuthTier.PARENT)
    assert not await auth_service.is_pin_set(AuthTier.PARENT)
    # No PIN = always passes
    assert await auth_service.verify_pin(AuthTier.PARENT, "anything")


@pytest.mark.asyncio
async def test_login_parent(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    result = await auth_service.login("1234")
    assert result is not None
    assert result["tier"] == "parent"
    assert "token" in result


@pytest.mark.asyncio
async def test_login_expert(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.EXPERT, "9999")
    result = await auth_service.login("9999")
    assert result is not None
    assert result["tier"] == "expert"


@pytest.mark.asyncio
async def test_login_wrong_pin(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    result = await auth_service.login("0000")
    assert result is None


@pytest.mark.asyncio
async def test_jwt_token_roundtrip(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    result = await auth_service.login("1234")
    assert result is not None

    claims = auth_service.verify_token(result["token"])
    assert claims is not None
    assert claims["tier"] == "parent"


@pytest.mark.asyncio
async def test_check_access_open(auth_service: AuthService) -> None:
    # Open tier always passes
    assert auth_service.check_access(None, AuthTier.OPEN)


@pytest.mark.asyncio
async def test_check_access_parent(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    result = await auth_service.login("1234")
    assert result is not None

    assert auth_service.check_access(result["token"], AuthTier.PARENT)
    assert not auth_service.check_access(None, AuthTier.PARENT)


@pytest.mark.asyncio
async def test_expert_has_parent_access(auth_service: AuthService) -> None:
    await auth_service.set_pin(AuthTier.EXPERT, "9999")
    result = await auth_service.login("9999")
    assert result is not None

    assert auth_service.check_access(result["token"], AuthTier.PARENT)
    assert auth_service.check_access(result["token"], AuthTier.EXPERT)


@pytest.mark.asyncio
async def test_invalid_token(auth_service: AuthService) -> None:
    assert auth_service.verify_token("garbage.token.here") is None
    # check_access with garbage token only fails when a PIN is set
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    assert not auth_service.check_access("garbage", AuthTier.PARENT)


@pytest.mark.asyncio
async def test_pin_min_length(auth_service: AuthService) -> None:
    with pytest.raises(ValueError, match="mindestens 4"):
        await auth_service.set_pin(AuthTier.PARENT, "12")


@pytest.mark.asyncio
async def test_check_access_bootstrap_open(auth_service: AuthService) -> None:
    """During initial setup no PIN is set — access must remain open."""
    assert auth_service.check_access(None, AuthTier.PARENT)
    assert auth_service.check_access(None, AuthTier.EXPERT)


@pytest.mark.asyncio
async def test_check_access_sealed_after_setup(auth_service: AuthService) -> None:
    """After setup completion the API must not fall open if a PIN is missing."""
    auth_service.set_setup_complete(True)
    assert not auth_service.check_access(None, AuthTier.PARENT)
    assert not auth_service.check_access(None, AuthTier.EXPERT)
    # Setting the PIN and logging in still works
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    result = await auth_service.login("1234")
    assert result is not None
    assert auth_service.check_access(result["token"], AuthTier.PARENT)


@pytest.mark.asyncio
async def test_start_reads_setup_complete(config_service) -> None:
    """start() must hydrate _setup_complete from config so the seal survives restarts."""
    await config_service.set("setup.step", "completed")
    service = AuthService(config_service)
    await service.start()
    # No PIN set + setup completed → access must be denied
    assert not service.check_access(None, AuthTier.PARENT)


@pytest.mark.asyncio
async def test_jwt_expiry_is_short_lived(auth_service: AuthService) -> None:
    """M3: tokens live hours, not a full day — limits blast radius of a stolen phone."""
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    result = await auth_service.login("1234")
    assert result is not None
    claims = auth_service.verify_token(result["token"])
    assert claims is not None
    assert _JWT_EXPIRE_HOURS <= 8, "token lifetime must stay short"
    # exp is within a few seconds of (now + lifetime)
    expected = int(time.time()) + _JWT_EXPIRE_HOURS * 3600
    assert abs(claims["exp"] - expected) < 5


@pytest.mark.asyncio
async def test_set_pin_rotates_secret_and_invalidates_tokens(auth_service: AuthService) -> None:
    """M3: changing a PIN must revoke any token that was issued before the change."""
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    result = await auth_service.login("1234")
    assert result is not None
    old_token = result["token"]
    # Old token verifies now
    assert auth_service.verify_token(old_token) is not None

    # Parent changes PIN — typical response to a suspected compromise
    await auth_service.set_pin(AuthTier.PARENT, "5678")

    # Old token must no longer verify (secret was rotated)
    assert auth_service.verify_token(old_token) is None
    # New login with the new PIN works and produces a different token
    new_result = await auth_service.login("5678")
    assert new_result is not None
    assert new_result["token"] != old_token
    assert auth_service.verify_token(new_result["token"]) is not None


@pytest.mark.asyncio
async def test_setting_expert_pin_also_rotates_parent_tokens(auth_service: AuthService) -> None:
    """Rotation is global — a PIN change on either tier invalidates all sessions."""
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    parent = await auth_service.login("1234")
    assert parent is not None

    await auth_service.set_pin(AuthTier.EXPERT, "9999")
    assert auth_service.verify_token(parent["token"]) is None


@pytest.mark.asyncio
async def test_remove_pin_rotates_secret(auth_service: AuthService) -> None:
    """W-3: removing a PIN is also a 'change the locks' event → old tokens must die."""
    await auth_service.set_pin(AuthTier.PARENT, "1234")
    login = await auth_service.login("1234")
    assert login is not None
    token = login["token"]
    assert auth_service.verify_token(token) is not None

    await auth_service.remove_pin(AuthTier.PARENT)
    assert auth_service.verify_token(token) is None
