"""Poll the status of one Remon device for all its entities."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER, SCAN_INTERVAL
from .remon_home_integration import (
    RemonClient,
    RemonError,
    RemonStatus,
    RemonUnsupportedApiError,
)

type RemonConfigEntry = ConfigEntry[RemonCoordinator]


class RemonCoordinator(DataUpdateCoordinator[RemonStatus]):
    """Read ``GET /api/status`` every :data:`SCAN_INTERVAL`."""

    config_entry: RemonConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RemonConfigEntry, client: RemonClient) -> None:
        """Poll ``client`` for the device of ``entry``."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.unique_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> RemonStatus:
        try:
            status = await self.client.get_status()
        except RemonUnsupportedApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unsupported_api",
                translation_placeholders={"api": str(err.api)},
            ) from err
        except RemonError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"host": self.client.host, "error": str(err)},
            ) from err

        if status.id != self.config_entry.unique_id:
            # The router gave this address to another Remon device. Discovery (mDNS or DHCP)
            # updates the host once it sees this entry's device again.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="wrong_device",
                translation_placeholders={
                    "host": self.client.host,
                    "found": status.id,
                    "expected": str(self.config_entry.unique_id),
                },
            )

        if self.data is not None and status.fw != self.data.fw:
            self._update_sw_version(status)
        return status

    def _update_sw_version(self, status: RemonStatus) -> None:
        """Show a firmware update on the device page without waiting for a reload."""
        dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, status.id)},
            sw_version=status.fw,
        )
