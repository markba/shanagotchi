"""Binary sensors for automations to hang off, such as a lamp that glows while a dose is due."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ShanagotchiConfigEntry, ShanagotchiCoordinator
from .entity import ShanagotchiEntity


@dataclass(frozen=True, kw_only=True)
class ShanagotchiBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[ShanagotchiCoordinator], bool]


BINARY_SENSORS = (
    ShanagotchiBinarySensorDescription(
        key="dose_due", value_fn=lambda c: c.engine.dose_due
    ),
    ShanagotchiBinarySensorDescription(
        key="checkin_pending", value_fn=lambda c: c.engine.checkin_pending(c.now)
    ),
    ShanagotchiBinarySensorDescription(
        key="refill_due", value_fn=lambda c: c.engine.refill_due(c.now)
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShanagotchiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ShanagotchiBinarySensor(entry.runtime_data, description)
        for description in BINARY_SENSORS
    )


class ShanagotchiBinarySensor(ShanagotchiEntity, BinarySensorEntity):
    entity_description: ShanagotchiBinarySensorDescription

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator)
