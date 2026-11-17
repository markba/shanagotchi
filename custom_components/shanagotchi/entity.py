"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShanagotchiCoordinator


class ShanagotchiEntity(CoordinatorEntity[ShanagotchiCoordinator]):
    """Subclasses use an entity description with a value_fn that takes the coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ShanagotchiCoordinator, description: EntityDescription
    ) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Shanagotchi",
            entry_type=DeviceEntryType.SERVICE,
        )
