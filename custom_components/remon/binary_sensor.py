"""Leak and salt sensor problem of a Remon device."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import RemonConfigEntry
from .entity import RemonEntity
from .remon_home_integration import RemonStatus

# The coordinator does the polling.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class RemonBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor reading one flag of the status."""

    value_fn: Callable[[RemonStatus], bool]


BINARY_SENSORS: tuple[RemonBinarySensorEntityDescription, ...] = (
    RemonBinarySensorEntityDescription(
        key="leak",
        translation_key="leak",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda status: status.leak,
    ),
    RemonBinarySensorEntityDescription(
        key="sensor_error",
        translation_key="sensor_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.sensor_error,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors of the device."""
    coordinator = entry.runtime_data
    async_add_entities(
        RemonBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class RemonBinarySensor(RemonEntity, BinarySensorEntity):
    """Binary sensor of a Remon device."""

    entity_description: RemonBinarySensorEntityDescription

    @property
    def is_on(self) -> bool:
        """Return the flag from the last status poll."""
        return self.entity_description.value_fn(self.coordinator.data)
