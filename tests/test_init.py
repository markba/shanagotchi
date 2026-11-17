from datetime import datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.shanagotchi.const import (
    ACTION_FEELING,
    CONF_BIN_CALENDAR,
    CONF_NOTIFY_SERVICE,
    DEFAULTS,
    DOMAIN,
)

MOOD = "sensor.shanagotchi_mood"


@pytest.fixture
async def melbourne(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await hass.config.async_set_time_zone("Australia/Melbourne")
    freezer.move_to(
        datetime(2026, 11, 2, 5, 59, tzinfo=dt_util.get_default_time_zone())
    )


async def setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options={**DEFAULTS, **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: int
) -> None:
    for _ in range(minutes):
        freezer.tick(60)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


async def test_config_flow_creates_entry_from_defaults(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULTS)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == DEFAULTS
    await hass.async_block_till_done()
    assert hass.states.get(MOOD) is not None


async def test_dose_lifecycle_notifies_and_survives_an_options_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, melbourne: None
) -> None:
    sent: list[dict] = []

    async def record(call: ServiceCall) -> None:
        sent.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_phone", record)
    entry = await setup(
        hass, sleep_end="05:00:00", **{CONF_NOTIFY_SERVICE: "notify.mobile_app_phone"}
    )

    await advance(hass, freezer, 1)
    assert hass.states.get(MOOD).state == "hungry"
    assert hass.states.get("binary_sensor.shanagotchi_dose_due").state == "on"
    assert [m["message"] for m in sent] == ["Time for your pills"]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {**entry.options, "max_repeats": 1}
    )
    await hass.async_block_till_done()
    assert hass.states.get(MOOD).state == "hungry"

    await hass.services.async_call(DOMAIN, "take_dose", blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get(MOOD)
    assert state.state == "happy"
    assert state.attributes["status"] == "taken"
    assert sent[-1] == {
        "title": "Shanagotchi",
        "message": "clear_notification",
        "data": {"tag": "shanagotchi_dose"},
    }


@pytest.mark.parametrize(("reply", "feeling"), [("4", 4), ("ok", 0), (" 2 ", 2)])
async def test_phone_reply_sets_feeling(
    hass: HomeAssistant, melbourne: None, reply: str, feeling: int
) -> None:
    await setup(hass)
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": ACTION_FEELING, "reply_text": reply},
    )
    await hass.async_block_till_done()
    assert hass.states.get(MOOD).attributes["feeling"] == feeling


async def test_bin_night_reads_the_next_collection_from_the_calendar(
    hass: HomeAssistant, melbourne: None
) -> None:
    async def get_events(call: ServiceCall) -> dict:
        return {
            "calendar.bins": {
                "events": [
                    {
                        "start": "2026-11-09",
                        "end": "2026-11-10",
                        "summary": "Recycling",
                    },
                    {"start": "2026-11-03", "end": "2026-11-04", "summary": "Rubbish"},
                    {"start": "2026-11-03", "end": "2026-11-04", "summary": "FOGO"},
                    {"start": "2026-11-01", "end": "2026-11-02", "summary": "Glass"},
                ]
            }
        }

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await setup(hass, **{CONF_BIN_CALENDAR: "calendar.bins"})

    assert (
        hass.states.get("sensor.shanagotchi_next_bin_collection").state == "2026-11-03"
    )
    attrs = hass.states.get(MOOD).attributes
    assert (attrs["bin_days"], attrs["bin_lids"]) == (1, ["red", "green"])


async def test_failing_bin_calendar_does_not_stop_doses(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, melbourne: None
) -> None:
    async def get_events(call: ServiceCall) -> dict:
        raise ConnectionError("calendar server down")

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await setup(hass, **{CONF_BIN_CALENDAR: "calendar.bins"})
    await advance(hass, freezer, 1)
    assert hass.states.get("binary_sensor.shanagotchi_dose_due").state == "on"


async def test_update_entity_keeps_entities_available(
    hass: HomeAssistant, melbourne: None
) -> None:
    await async_setup_component(hass, "homeassistant", {})
    await setup(hass)
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": MOOD}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(MOOD).state != "unavailable"


async def test_taking_after_a_sleep_cannot_claim_a_dose_whose_window_closed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, melbourne: None
) -> None:
    await setup(hass, sleep_end="05:00:00")
    await advance(hass, freezer, 1)
    freezer.move_to(datetime(2026, 11, 2, 9, 0, tzinfo=dt_util.get_default_time_zone()))
    await hass.services.async_call(DOMAIN, "take_dose", blocking=True)
    await hass.async_block_till_done()
    attrs = hass.states.get(MOOD).attributes
    assert (attrs["status"], attrs["notice"]) == ("waiting", "Missed 06:00 dose")
