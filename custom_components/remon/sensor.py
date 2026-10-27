"""Salt level sensor of a Remon device."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import RemonConfigEntry
from .entity import RemonEntity
from .remon_home_integration import RemonStatus

# The coordinator does the polling.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class RemonSensorEntityDescription(SensorEntityDescription):
    """Sensor reading one field of the status."""

    value_fn: Callable[[RemonStatus], StateType]


SENSORS: tuple[RemonSensorEntityDescription, ...] = (
    RemonSensorEntityDescription(
        key="salt_level",
        translation_key="salt_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        # A level read while the salt sensor reports a fault cannot be trusted, so it is
        # unknown rather than a stale number that could keep (or start) a low-salt alert.
        value_fn=lambda status: None if status.sensor_error else status.salt_level,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors of the device."""
    coordinator = entry.runtime_data
    async_add_entities(RemonSensor(coordinator, description) for description in SENSORS)


class RemonSensor(RemonEntity, SensorEntity):
    """Sensor of a Remon device."""

    entity_description: RemonSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the value from the last status poll."""
        return self.entity_description.value_fn(self.coordinator.data)
