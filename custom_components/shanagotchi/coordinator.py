"""Runs the engine each minute, persists its state, sends notifications and reads the bin calendar."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import engine as eng
from .const import (
    ACTION_FEELING,
    ACTION_ORDERED,
    ACTION_SKIP,
    ACTION_TAKEN,
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
    DOMAIN,
    LOGGER,
    TAG_DOSE,
    TAG_FEELING,
    TAG_REFILL,
)

type ShanagotchiConfigEntry = ConfigEntry[ShanagotchiCoordinator]

STORAGE_VERSION = 1
BIN_LOOKAHEAD = timedelta(days=60)
BIN_REFRESH = timedelta(hours=1)
# The calendar can load after this integration, so a failed read is retried soon
BIN_RETRY = timedelta(minutes=1)
TITLE = "Shanagotchi"
CLEAR = "clear_notification"

FEELING_ACTIONS = [
    {"action": ACTION_FEELING, "title": "Answer 1-5", "behavior": "textInput"}
]
# Event -> (message, tag, actions). The refill message has {name} filled in when sent
NOTIFICATIONS = {
    eng.ALERT: (
        "Time for your pills",
        TAG_DOSE,
        [
            {"action": ACTION_TAKEN, "title": "Taken"},
            {"action": ACTION_SKIP, "title": "Skip"},
        ],
    ),
    eng.ASK_FEELING: (
        "How are you feeling today? 1 to 5",
        TAG_FEELING,
        FEELING_ACTIONS,
    ),
    eng.BAD_FEELING: ("Just a number from 1 to 5", TAG_FEELING, FEELING_ACTIONS),
    eng.REFILL: (
        "Time to order {name}",
        TAG_REFILL,
        [{"action": ACTION_ORDERED, "title": "Ordered"}],
    ),
    eng.CLEAR_DOSE: (CLEAR, TAG_DOSE, None),
    eng.CLEAR_FEELING: (CLEAR, TAG_FEELING, None),
    eng.CLEAR_REFILL: (CLEAR, TAG_REFILL, None),
}


def settings_from_options(options: dict) -> eng.Settings:
    doses = int(options[CONF_DOSES_PER_DAY])
    return eng.Settings(
        dose_times=tuple(
            time.fromisoformat(options[k]) for k in CONF_DOSE_TIMES[:doses]
        ),
        dose_window=timedelta(minutes=options[CONF_DOSE_WINDOW]),
        early_window=timedelta(minutes=options[CONF_EARLY_WINDOW]),
        repeat=timedelta(minutes=options[CONF_REPEAT]),
        max_repeats=int(options[CONF_MAX_REPEATS]),
        checkin_time=time.fromisoformat(options[CONF_CHECKIN_TIME]),
        sleep_start=time.fromisoformat(options[CONF_SLEEP_START]),
        sleep_end=time.fromisoformat(options[CONF_SLEEP_END]),
        refill_name=options.get(CONF_REFILL_NAME, "").strip(),
        refill_interval_days=int(options[CONF_REFILL_INTERVAL]),
    )


class ShanagotchiCoordinator(DataUpdateCoordinator[None]):
    config_entry: ShanagotchiConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ShanagotchiConfigEntry) -> None:
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry)
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, DOMAIN)
        self.engine: eng.Engine
        self.bin_date: date | None = None
        self.bin_types: list[str] = []
        self._next_bin_refresh: datetime | None = None

    async def async_start(self) -> None:
        stored = await self._store.async_load()
        self.engine = eng.Engine(
            settings_from_options(self.config_entry.options),
            eng.State.from_dict(stored) if stored else eng.State(),
        )
        await self._async_tick(dt_util.now())
        self.config_entry.async_on_unload(
            async_track_time_change(self.hass, self._async_tick, second=0)
        )
        self.config_entry.async_on_unload(
            self.hass.bus.async_listen(
                "mobile_app_notification_action", self._async_on_notification_action
            )
        )

    async def async_save(self) -> None:
        await self._store.async_save(self.engine.state.as_dict())

    @property
    def now(self) -> datetime:
        return dt_util.now()

    async def _async_update_data(self) -> None:
        """Nothing to fetch. Without this, homeassistant.update_entity marks every entity unavailable."""

    async def async_resolve(self, outcome: str) -> None:
        await self._async_act(lambda now: self.engine.resolve(now, outcome))

    async def async_set_feeling(self, value: int) -> None:
        await self._async_act(lambda now: self.engine.set_feeling(value))

    async def async_refill_ordered(self) -> None:
        await self._async_act(self.engine.refill_ordered)

    async def _async_act(self, action: Callable[[datetime], list[str]]) -> None:
        # Tick first, so an action straight after a sleep can't land on a dose whose window has closed
        now = self.now
        await self._async_apply(self.engine.tick(now) + action(now))

    async def _async_tick(self, now: datetime) -> None:
        before = replace(self.engine.state, last_tick=None)
        events = self.engine.tick(now)
        # last_tick moves every minute, which alone isn't worth a write to disk
        changed = before != replace(self.engine.state, last_tick=None)
        await self._async_apply(events, save=changed)
        # The calendar comes last. It can be slow, and a tick must not sit on its events while it waits
        if self._next_bin_refresh is None or now >= self._next_bin_refresh:
            self._next_bin_refresh = now + BIN_RETRY
            if await self._async_refresh_bins(now):
                # Never later than midnight, when the days-until count changes
                self._next_bin_refresh = min(
                    now + BIN_REFRESH,
                    dt_util.start_of_local_day(now + timedelta(days=1)),
                )
                self.async_update_listeners()

    async def _async_on_notification_action(self, event: Event) -> None:
        action = event.data.get("action")
        if action == ACTION_TAKEN:
            await self.async_resolve("taken")
        elif action == ACTION_SKIP:
            await self.async_resolve("skipped")
        elif action == ACTION_ORDERED:
            await self.async_refill_ordered()
        elif action == ACTION_FEELING:
            reply = str(event.data.get("reply_text", "")).strip()
            await self.async_set_feeling(int(reply) if reply.isdecimal() else 0)

    async def _async_apply(self, events: list[str], save: bool = True) -> None:
        if save:
            self._store.async_delay_save(self.engine.state.as_dict, 1)
        self.async_update_listeners()
        for event in events:
            await self._async_notify(event)

    async def _async_notify(self, event: str) -> None:
        service = self.config_entry.options.get(CONF_NOTIFY_SERVICE)
        if not service:
            return
        message, tag, actions = NOTIFICATIONS[event]
        data = {"tag": tag, "actions": actions} if actions else {"tag": tag}
        domain, _, name = service.partition(".")
        try:
            await self.hass.services.async_call(
                domain,
                name,
                {
                    "title": TITLE,
                    "message": message.format(name=self.engine.settings.refill_name),
                    "data": data,
                },
            )
        except HomeAssistantError as err:
            LOGGER.warning("Could not send %s through %s: %s", event, service, err)

    async def _async_refresh_bins(self, now: datetime) -> bool:
        calendar = self.config_entry.options.get(CONF_BIN_CALENDAR)
        if not calendar:
            return True
        start = dt_util.start_of_local_day(now)
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": calendar,
                    "start_date_time": start.isoformat(),
                    "end_date_time": (start + BIN_LOOKAHEAD).isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001
            # Calendar integrations raise all sorts on a network blip, and it must not stop the doses
            LOGGER.debug("Bin calendar %s not readable: %s", calendar, err)
            return False
        by_day: dict[date, list[str]] = {}
        for event in response.get(calendar, {}).get("events", []):
            start_at = dt_util.parse_datetime(event["start"])
            day = (
                dt_util.as_local(start_at).date()
                if start_at
                else date.fromisoformat(event["start"])
            )
            if day >= now.date():
                by_day.setdefault(day, []).append(event["summary"])
        self.bin_date = min(by_day, default=None)
        self.bin_types = by_day.get(self.bin_date, [])
        return True
