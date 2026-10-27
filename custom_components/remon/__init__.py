"""The Remon integration: salt level, leak and salt sensor problem of Remon devices on the LAN."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import RemonConfigEntry, RemonCoordinator
from .remon_home_integration import RemonClient

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: RemonConfigEntry) -> bool:
    """Set up a Remon device from a config entry."""
    client = RemonClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    coordinator = RemonCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RemonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
