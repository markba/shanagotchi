"""Config and options flow. Both show the same settings form."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector as sel

from .const import (
    CONF_BIN_CALENDAR,
    CONF_CHECKIN_TIME,
    CONF_DOSE_TIMES,
    CONF_DOSE_WINDOW,
    CONF_DOSES_PER_DAY,
    CONF_EARLY_WINDOW,
    CONF_MAX_REPEATS,
    CONF_NOTIFY_SERVICE,
    CONF_REFILL_INTERVAL,
    CONF_REFILL_NAME,
    CONF_REPEAT,
    CONF_SLEEP_END,
    CONF_SLEEP_START,
    DEFAULTS,
    DOMAIN,
)
from .coordinator import ShanagotchiConfigEntry


def _number(low: int, high: int, step: int = 1, unit: str | None = None):
    config = sel.NumberSelectorConfig(
        min=low, max=high, step=step, mode=sel.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return sel.NumberSelector(config)


def settings_schema(hass: HomeAssistant) -> vol.Schema:
    # Actionable notifications need the Companion app's notify services, which no selector lists
    notify_services = sorted(
        f"notify.{name}"
        for name in hass.services.async_services_for_domain("notify")
        if name.startswith("mobile_app_")
    )
    return vol.Schema(
        {
            vol.Required(CONF_DOSES_PER_DAY): _number(1, 3),
            **{vol.Required(key): sel.TimeSelector() for key in CONF_DOSE_TIMES},
            vol.Required(CONF_DOSE_WINDOW): _number(15, 720, 5, "min"),
            vol.Required(CONF_EARLY_WINDOW): _number(0, 180, 5, "min"),
            vol.Required(CONF_REPEAT): _number(5, 120, 5, "min"),
            vol.Required(CONF_MAX_REPEATS): _number(0, 10),
            vol.Required(CONF_CHECKIN_TIME): sel.TimeSelector(),
            vol.Required(CONF_SLEEP_START): sel.TimeSelector(),
            vol.Required(CONF_SLEEP_END): sel.TimeSelector(),
            vol.Optional(CONF_NOTIFY_SERVICE): sel.SelectSelector(
                sel.SelectSelectorConfig(
                    options=notify_services,
                    custom_value=True,
                    mode=sel.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_BIN_CALENDAR): sel.EntitySelector(
                sel.EntitySelectorConfig(domain="calendar")
            ),
            vol.Optional(CONF_REFILL_NAME): sel.TextSelector(),
            vol.Required(CONF_REFILL_INTERVAL): _number(1, 120, 1, "d"),
        }
    )


class ShanagotchiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ShanagotchiConfigEntry,
    ) -> ShanagotchiOptionsFlow:
        return ShanagotchiOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Shanagotchi", data={}, options=user_input
            )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                settings_schema(self.hass), DEFAULTS
            ),
        )


class ShanagotchiOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                settings_schema(self.hass), self.config_entry.options
            ),
        )
