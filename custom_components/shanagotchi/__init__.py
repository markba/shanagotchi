"""Shanagotchi: dose reminders, a daily check-in, bin night and a character whose mood follows them."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    SERVICE_REFILL_ORDERED,
    SERVICE_SET_FEELING,
    SERVICE_SKIP_DOSE,
    SERVICE_TAKE_DOSE,
    STATIC_URL,
)
from .coordinator import ShanagotchiConfigEntry, ShanagotchiCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # Registered here and not per entry, because an options change reloads the entry
    # and a static path can only be registered once
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), False)]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/shanagotchi-card.js?v={integration.version}")

    def coordinator() -> ShanagotchiCoordinator:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("Shanagotchi is not set up")
        return entries[0].runtime_data

    async def take_dose(call: ServiceCall) -> None:
        await coordinator().async_resolve("taken")

    async def skip_dose(call: ServiceCall) -> None:
        await coordinator().async_resolve("skipped")

    async def set_feeling(call: ServiceCall) -> None:
        await coordinator().async_set_feeling(call.data["value"])

    async def refill_ordered(call: ServiceCall) -> None:
        await coordinator().async_refill_ordered()

    hass.services.async_register(DOMAIN, SERVICE_TAKE_DOSE, take_dose)
    hass.services.async_register(DOMAIN, SERVICE_SKIP_DOSE, skip_dose)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FEELING,
        set_feeling,
        schema=vol.Schema(
            {vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(1, 5))}
        ),
    )
    hass.services.async_register(DOMAIN, SERVICE_REFILL_ORDERED, refill_ordered)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ShanagotchiConfigEntry) -> bool:
    coordinator = ShanagotchiCoordinator(hass, entry)
    await coordinator.async_start()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ShanagotchiConfigEntry
) -> bool:
    # An options change reloads straight away, before the delayed save has run
    await entry.runtime_data.async_save()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
