"""Constants for Shanagotchi."""

import logging

DOMAIN = "shanagotchi"
LOGGER = logging.getLogger(__package__)

STATIC_URL = "/shanagotchi_static"

CONF_DOSES_PER_DAY = "doses_per_day"
CONF_DOSE_TIMES = ("dose_1_time", "dose_2_time", "dose_3_time")
CONF_DOSE_WINDOW = "dose_window_min"
CONF_EARLY_WINDOW = "early_window_min"
CONF_REPEAT = "repeat_min"
CONF_MAX_REPEATS = "max_repeats"
CONF_CHECKIN_TIME = "checkin_time"
CONF_SLEEP_START = "sleep_start"
CONF_SLEEP_END = "sleep_end"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_BIN_CALENDAR = "bin_calendar"
CONF_REFILL_NAME = "refill_name"
CONF_REFILL_INTERVAL = "refill_interval_days"

DEFAULTS = {
    CONF_DOSES_PER_DAY: 1,
    CONF_DOSE_TIMES[0]: "06:00:00",
    CONF_DOSE_TIMES[1]: "13:00:00",
    CONF_DOSE_TIMES[2]: "20:00:00",
    CONF_DOSE_WINDOW: 120,
    CONF_EARLY_WINDOW: 60,
    CONF_REPEAT: 30,
    CONF_MAX_REPEATS: 4,
    CONF_CHECKIN_TIME: "18:00:00",
    CONF_SLEEP_START: "22:00:00",
    CONF_SLEEP_END: "07:00:00",
    CONF_REFILL_INTERVAL: 20,
}

# Namespaced because every automation sees every Companion app notification action
ACTION_TAKEN = "SHANAGOTCHI_TAKEN"
ACTION_SKIP = "SHANAGOTCHI_SKIP"
ACTION_FEELING = "SHANAGOTCHI_FEELING"
ACTION_ORDERED = "SHANAGOTCHI_ORDERED"

TAG_DOSE = "shanagotchi_dose"
TAG_FEELING = "shanagotchi_feeling"
TAG_REFILL = "shanagotchi_refill"

SERVICE_TAKE_DOSE = "take_dose"
SERVICE_SKIP_DOSE = "skip_dose"
SERVICE_SET_FEELING = "set_feeling"
SERVICE_REFILL_ORDERED = "refill_ordered"
