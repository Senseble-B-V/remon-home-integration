"""Tests for the salt level sensor and the leak and salt sensor binary sensors."""

from __future__ import annotations

import pytest
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import DEVICE_ID, STATUS_URL, load_fixture, setup_entry, state_of

SALT_LEVEL = "sensor.saltbuddy_salt_level"
LEAK = "binary_sensor.saltbuddy_leak"
SALT_SENSOR = "binary_sensor.saltbuddy_salt_sensor"


async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, mock_config_entry)

    state = hass.states.get(SALT_LEVEL)
    assert state is not None
    assert state.state == "64"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == PERCENTAGE
    assert state.attributes["friendly_name"] == "SaltBuddy Salt level"

    state = hass.states.get(LEAK)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_DEVICE_CLASS] == "moisture"

    state = hass.states.get(SALT_SENSOR)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_DEVICE_CLASS] == "problem"

    for entity_id, key in ((SALT_LEVEL, "salt_level"), (LEAK, "leak")):
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.unique_id == f"{DEVICE_ID}_{key}"
        assert entry.entity_category is None
    entry = entity_registry.async_get(SALT_SENSOR)
    assert entry is not None
    assert entry.unique_id == f"{DEVICE_ID}_sensor_error"
    assert entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_leak(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    aioclient_mock.get(
        STATUS_URL, text=load_fixture("saltbuddy.json").replace('"leak":false', '"leak":true')
    )
    await setup_entry(hass, mock_config_entry)
    assert state_of(hass, LEAK) == STATE_ON


@pytest.mark.parametrize(
    "body",
    [
        # No salt sample yet: the firmware sends null and flags an error.
        load_fixture("saltbuddy.json").replace(
            '"salt_level":64,"sensor_error":false', '"salt_level":null,"sensor_error":true'
        ),
        # A sensor fault with a level still cached: the level is not trusted.
        load_fixture("saltbuddy.json").replace('"sensor_error":false', '"sensor_error":true'),
    ],
)
async def test_salt_sensor_error_makes_level_unknown(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    body: str,
) -> None:
    aioclient_mock.get(STATUS_URL, text=body)
    await setup_entry(hass, mock_config_entry)
    assert state_of(hass, SALT_LEVEL) == STATE_UNKNOWN
    assert state_of(hass, SALT_SENSOR) == STATE_ON


async def test_empty_salt(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    aioclient_mock.get(STATUS_URL, text=load_fixture("saltbuddy.json").replace("64", "0"))
    await setup_entry(hass, mock_config_entry)
    assert state_of(hass, SALT_LEVEL) == "0"
