"""Tests for WiFi service (mock mode on non-Pi)."""

import pytest

from core.services.wifi_service import WifiService


@pytest.mark.asyncio
async def test_scan_returns_mock_networks() -> None:
    service = WifiService()
    networks = await service.scan()
    assert len(networks) > 0
    assert all(n.ssid for n in networks)


@pytest.mark.asyncio
async def test_mock_connect() -> None:
    service = WifiService()
    result = await service.connect("TestNetwork", "password")
    assert result is True


@pytest.mark.asyncio
async def test_status_mock() -> None:
    service = WifiService()
    status = await service.status()
    assert hasattr(status, "connected")
    assert hasattr(status, "ssid")


@pytest.mark.asyncio
async def test_network_fields() -> None:
    from dataclasses import asdict
    service = WifiService()
    networks = await service.scan()
    d = asdict(networks[0])
    assert "ssid" in d
    assert "signal" in d
    assert "security" in d
