"""Fixtures for the Home Assistant integration tests.

These tests run in their own pytest session with Home Assistant's test plugin (see README.md,
"Develop"): the plugin blocks sockets and checks for lingering threads, which the client tests in
``tests/`` need. They drive the bundled client for real against ``aioclient_mock``, replaying
the recorded device responses from ``tests/fixtures``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.remon.const import DOMAIN

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

HOST = "192.168.1.42"
STATUS_URL = f"http://{HOST}/api/status"
DEVICE_ID = "SaltBuddy-a1b2c3d4e5f6"
MAC = "a1:b2:c3:d4:e5:f6"


def load_fixture(name: str) -> str:
    """Return a recorded ``/api/status`` body."""
    return (FIXTURES / name).read_text()


def mock_status(
    aioclient_mock: AiohttpClientMocker, fixture: str = "saltbuddy.json", host: str = HOST
) -> None:
    """Answer ``GET /api/status`` on ``host`` with a recorded body, replacing earlier mocks."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"http://{host}/api/status", text=load_fixture(fixture))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components/."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Config entry of the SaltBuddy in ``tests/fixtures/saltbuddy.json``."""
    return MockConfigEntry(
        domain=DOMAIN, title="SaltBuddy", unique_id=DEVICE_ID, data={CONF_HOST: HOST}
    )


@pytest.fixture
def device(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """A SaltBuddy answering at :data:`HOST`."""
    mock_status(aioclient_mock)
    return aioclient_mock


def state_of(hass: HomeAssistant, entity_id: str) -> str:
    """Return the state of an entity that must exist."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add ``entry`` and set it up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
