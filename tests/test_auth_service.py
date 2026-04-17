"""Tests for the auth service."""

from pathlib import Path

import pytest

from core.services.auth_service import AuthService, AuthTier
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
