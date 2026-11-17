"""Sensors. The mood sensor's attributes carry everything the dashboard card draws."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ShanagotchiConfigEntry, ShanagotchiCoordinator
from .engine import MOODS, STATUSES, lid_colours
from .entity import ShanagotchiEntity


@dataclass(frozen=True, kw_only=True)
class ShanagotchiSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ShanagotchiCoordinator], Any]
    attrs_fn: Callable[[ShanagotchiCoordinator], dict[str, Any]] | None = None


def _mood_attrs(c: ShanagotchiCoordinator) -> dict[str, Any]:
    now, state = c.now, c.engine.state
    return {
        "status": state.status,
        "status_changed": state.status_changed,
        "next_dose": c.engine.next_dose(now).strftime("%H:%M"),
        "notice": state.notice,
        "streak_days": state.streak_days,
        "feeling": state.feeling,
        "checkin_pending": c.engine.checkin_pending(now),
        "refill_due": c.engine.refill_due(now),
        "refill_name": c.engine.settings.refill_name,
        "bin_date": c.bin_date,
        "bin_days": (c.bin_date - now.date()).days if c.bin_date else None,
        "bin_lids": lid_colours(c.bin_types),
    }


SENSORS = (
    ShanagotchiSensorDescription(
        key="mood",
        device_class=SensorDeviceClass.ENUM,
        options=MOODS,
        value_fn=lambda c: c.engine.mood(c.now),
        attrs_fn=_mood_attrs,
    ),
    ShanagotchiSensorDescription(
        key="dose_status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUSES,
        value_fn=lambda c: c.engine.state.status,
    ),
    ShanagotchiSensorDescription(
        key="feeling",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.engine.state.feeling or None,
    ),
    ShanagotchiSensorDescription(
        key="doses_taken_today",
        value_fn=lambda c: c.engine.state.taken_today,
    ),
    ShanagotchiSensorDescription(
        key="doses_missed_today",
        value_fn=lambda c: c.engine.state.missed_today,
    ),
    ShanagotchiSensorDescription(
        key="streak",
        value_fn=lambda c: c.engine.state.streak_days,
    ),
    ShanagotchiSensorDescription(
        key="next_bin_collection",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda c: c.bin_date,
        attrs_fn=lambda c: {"types": c.bin_types},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShanagotchiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ShanagotchiSensor(entry.runtime_data, description) for description in SENSORS
    )


class ShanagotchiSensor(ShanagotchiEntity, SensorEntity):
    entity_description: ShanagotchiSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        return attrs_fn(self.coordinator) if attrs_fn else None
