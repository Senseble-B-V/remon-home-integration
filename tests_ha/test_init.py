"""Tests for setting up and unloading a config entry, and the polling coordinator."""

from __future__ import annotations

from typing import Any

import pytest
from aiohttp import ClientError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.remon.const import DOMAIN, SCAN_INTERVAL

from .conftest import (
    DEVICE_ID,
    MAC,
    STATUS_URL,
    load_fixture,
    mock_status,
    setup_entry,
    state_of,
)

SALT_LEVEL = "sensor.saltbuddy_salt_level"


async def poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Let the coordinator poll once."""
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, device: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    await setup_entry(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert device.call_count == 1
    (_, _, _, headers) = device.mock_calls[0]
    assert headers["Connection"] == "close"

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    # Read the state again: mypy keeps the LOADED narrowing from above across the unload.
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert entry is not None
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_device_registry(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    device: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, mock_config_entry)
    (entry,) = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
    assert entry.identifiers == {(DOMAIN, DEVICE_ID)}
    assert entry.connections == {(dr.CONNECTION_NETWORK_MAC, MAC)}
    assert entry.manufacturer == "Remon"
    assert entry.model == "SaltBuddy"
    assert entry.name == "SaltBuddy"
    assert entry.sw_version == "382de8e"


async def test_device_without_mac_in_id(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        STATUS_URL,
        json={
            "id": "Future",
            "type": "Future",
            "fw": "abcdef0",
            "salt_level": 50,
            "sensor_error": False,
            "leak": False,
        },
    )
    entry = MockConfigEntry(domain=DOMAIN, unique_id="Future", data={"host": "192.168.1.42"})
    await setup_entry(hass, entry)
    (device,) = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert device.identifiers == {(DOMAIN, "Future")}
    assert device.connections == set()
    assert device.name == "Remon device"


@pytest.mark.parametrize(
    "mock_kwargs",
    [
        {"exc": ClientError()},
        {"json": {"id": DEVICE_ID, "api": 99}},
        # Another device now has the configured address.
        {"text": load_fixture("softener_df_leak.json")},
    ],
)
async def test_setup_retries(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    mock_kwargs: dict[str, Any],
) -> None:
    aioclient_mock.get(STATUS_URL, **mock_kwargs)
    await setup_entry(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize(
    "mock_kwargs",
    [
        {"exc": ClientError()},
        {"json": {"id": DEVICE_ID, "api": 99}},
        {"text": load_fixture("softener_df_leak.json")},
    ],
)
async def test_poll_failure_makes_entities_unavailable(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    mock_kwargs: dict[str, Any],
) -> None:
    mock_status(aioclient_mock)
    await setup_entry(hass, mock_config_entry)
    assert state_of(hass, SALT_LEVEL) == "64"

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATUS_URL, **mock_kwargs)
    await poll(hass, freezer)
    assert state_of(hass, SALT_LEVEL) == STATE_UNAVAILABLE

    mock_status(aioclient_mock)
    await poll(hass, freezer)
    assert state_of(hass, SALT_LEVEL) == "64"


async def test_firmware_update_updates_device(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    device_registry: dr.DeviceRegistry,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_status(aioclient_mock)
    await setup_entry(hass, mock_config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        STATUS_URL, text=load_fixture("saltbuddy.json").replace("382de8e", "4a5b6c7")
    )
    await poll(hass, freezer)
    (device,) = dr.async_entries_for_config_entry(device_registry, mock_config_entry.entry_id)
    assert device.sw_version == "4a5b6c7"
