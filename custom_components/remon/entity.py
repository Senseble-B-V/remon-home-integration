"""Base entity for Remon devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RemonCoordinator
from .remon_home_integration import MANUFACTURER


class RemonEntity(CoordinatorEntity[RemonCoordinator]):
    """One reading of a Remon device, on a device named after its family."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RemonCoordinator, description: EntityDescription) -> None:
        """Describe the entity and its device from the first status poll."""
        super().__init__(coordinator)
        self.entity_description = description
        status = coordinator.data
        self._attr_unique_id = f"{status.id}_{description.key}"
        # The MAC lets DHCP discovery's registered_devices matcher recognise the device.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, status.id)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if (mac := status.mac) else set(),
            manufacturer=MANUFACTURER,
            model=status.display_name,
            name=status.display_name,
            sw_version=status.fw,
        )
