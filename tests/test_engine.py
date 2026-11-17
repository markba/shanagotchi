from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.shanagotchi import engine as eng

TZ = ZoneInfo("Australia/Melbourne")


def at(hhmm: str, day: int = 2) -> datetime:
    return datetime.combine(date(2026, 11, day), time.fromisoformat(hhmm), tzinfo=TZ)


def make(*dose_times: str, **state) -> eng.Engine:
    settings = eng.Settings(
        dose_times=tuple(time.fromisoformat(t) for t in dose_times or ("06:00",)),
        dose_window=timedelta(minutes=120),
        early_window=timedelta(minutes=60),
        repeat=timedelta(minutes=30),
        max_repeats=2,
        checkin_time=time(18),
        sleep_start=time(22),
        sleep_end=time(7),
        refill_name="Coffee beans",
        refill_interval_days=20,
    )
    return eng.Engine(settings, eng.State(**state))


def run(
    engine: eng.Engine, start: str, end: str, day: int = 2
) -> list[tuple[str, str]]:
    """Tick every minute like HA does and return (HH:MM, event) pairs."""
    out = []
    now = at(start, day)
    while now <= at(end, day):
        out += [(f"{now:%H:%M}", e) for e in engine.tick(now)]
        now += timedelta(minutes=1)
    return out


def test_dose_falls_due_then_taken():
    e = make()
    assert run(e, "05:59", "06:00") == [("06:00", eng.ALERT)]
    assert e.mood(at("06:00")) == "hungry"
    assert e.resolve(at("06:10"), "taken") == [eng.CLEAR_DOSE]
    s = e.state
    assert (s.status, s.taken_today, s.due_since) == ("taken", 1, None)
    assert e.mood(at("08:00")) == "happy"


def test_ignored_dose_repeats_then_is_missed_at_window_close():
    e = make()
    events = run(e, "05:59", "08:00")
    assert events == [
        ("06:00", eng.ALERT),
        ("06:30", eng.ALERT),
        ("07:00", eng.ALERT),
        ("08:00", eng.CLEAR_DOSE),
    ]
    s = e.state
    assert (s.status, s.missed_today, s.notice) == ("waiting", 1, "Missed 06:00 dose")
    assert e.mood(at("08:00")) == "sad"


def test_missed_notice_survives_midnight_until_next_dose_resolved():
    e = make()
    run(e, "05:59", "08:00")
    e.tick(at("00:00", day=3))
    assert e.state.notice == "Missed 06:00 dose"
    assert (e.state.missed_today, e.state.streak_days) == (0, 0)
    e.tick(at("06:00", day=3))
    e.resolve(at("06:01", day=3), "skipped")
    assert (e.state.notice, e.state.status, e.state.taken_today) == ("", "skipped", 0)


def test_early_take_counts_once_and_stops_the_dose_firing():
    e = make("13:00")
    assert e.resolve(at("11:30"), "taken") == []
    assert e.resolve(at("12:30"), "taken") == [eng.CLEAR_DOSE]
    assert e.resolve(at("12:40"), "taken") == []
    assert e.state.taken_today == 1
    assert run(e, "12:41", "13:05") == []
    assert e.state.status == "taken"


def test_midnight_dose_opens_after_the_day_rolls_over():
    e = make("00:00", streak_days=2)
    e.tick(at("23:59"))
    assert e.tick(at("00:00", day=3)) == [eng.ALERT]
    assert (e.state.status, e.state.missed_today, e.state.streak_days) == ("due", 0, 3)


def test_early_take_reaches_a_dose_just_after_midnight():
    e = make("00:15")
    assert e.resolve(at("23:40"), "taken") == [eng.CLEAR_DOSE]
    assert run(e, "00:00", "00:20", day=3) == []


def test_dose_time_repeated_when_daylight_saving_ends_fires_once():
    e = make("02:30")
    # 02:29 daylight time on 05/04/2026. The clock goes back from 03:00 to 02:00, so 02:30 comes twice
    start = datetime(2026, 4, 4, 15, 29, tzinfo=UTC)
    events = [
        ev
        for m in range(70)
        for ev in e.tick((start + timedelta(minutes=m)).astimezone(TZ))
    ]
    assert eng.CLEAR_DOSE not in events
    assert (e.dose_due, e.state.missed_today) == (True, 0)


def test_due_dose_is_dropped_when_its_time_leaves_the_settings():
    e = make("06:00")
    e.tick(at("06:00"))
    moved = eng.Engine(make("09:00").settings, e.state)
    assert moved.tick(at("06:10")) == [eng.CLEAR_DOSE]
    assert (moved.dose_due, moved.state.status) == (False, "waiting")


def test_next_dose_falling_due_misses_the_one_still_open():
    e = make("06:00", "07:00")
    run(e, "05:59", "07:00")
    assert (e.state.missed_today, e.state.status) == (1, "due")
    assert e.state.due_since == at("07:00")


@pytest.mark.parametrize(
    ("asleep_until", "expect_status", "expect_missed", "expect_events"),
    [
        # Woke inside the window: the dose is due now
        ("07:30", "due", 0, [eng.ALERT]),
        # The whole window passed while HA was off: not judged either way
        ("09:00", "waiting", 0, []),
    ],
)
def test_dose_time_crossed_while_ha_was_not_running(
    asleep_until, expect_status, expect_missed, expect_events
):
    e = make()
    e.tick(at("05:00"))
    assert e.tick(at(asleep_until)) == expect_events
    assert (e.state.status, e.state.missed_today) == (expect_status, expect_missed)


def test_dose_already_due_before_a_gap_is_missed_when_its_window_closed():
    e = make()
    run(e, "05:59", "06:05")
    assert e.tick(at("09:00")) == [eng.CLEAR_DOSE]
    assert e.state.missed_today == 1


def test_streak_counts_clean_days_and_resets_on_a_miss():
    e = make(streak_days=3)
    e.tick(at("23:59"))
    e.tick(at("00:00", day=3))
    assert e.state.streak_days == 4
    run(e, "05:59", "08:00", day=3)
    e.tick(at("00:00", day=4))
    assert e.state.streak_days == 0


def test_several_midnights_crossed_count_one_day():
    e = make(streak_days=3, taken_today=1, feeling=4)
    e.tick(at("21:00"))
    e.tick(at("12:00", day=5))
    s = e.state
    assert (s.streak_days, s.taken_today, s.feeling) == (4, 0, 0)


def test_checkin_asks_at_its_time_reasks_once_and_stops_when_answered():
    e = make()
    e.tick(at("17:00"))
    assert e.mood(at("17:59")) == "okay"
    events = run(e, "17:59", "21:59")
    assert events == [("18:00", eng.ASK_FEELING), ("20:00", eng.ASK_FEELING)]
    assert e.mood(at("21:00")) == "ask"
    assert e.set_feeling(7) == [eng.BAD_FEELING]
    assert e.set_feeling(2) == [eng.CLEAR_FEELING]
    assert e.mood(at("21:00")) == "low"


def test_sleep_window_wraps_midnight_and_a_due_dose_wins():
    e = make("23:00")
    e.tick(at("22:00"))
    assert e.mood(at("22:30")) == "sleep"
    assert e.mood(at("06:59", day=3)) == "sleep"
    e.tick(at("23:00"))
    assert e.mood(at("23:00")) == "hungry"


def test_refill_reminds_daily_from_ten_until_ordered():
    e = make(refill_last_ordered=date(2026, 10, 13))
    assert not e.refill_due(at("12:00", day=1))
    e.tick(at("09:00"))
    assert run(e, "09:01", "11:00") == [("10:00", eng.REFILL)]
    assert e.refill_ordered(at("11:00")) == [eng.CLEAR_REFILL]
    assert not e.refill_due(at("11:00"))


def test_state_round_trips_through_storage():
    e = make(refill_last_ordered=date(2026, 10, 13))
    run(e, "05:59", "06:10")
    restored = eng.State.from_dict(e.state.as_dict())
    assert restored == e.state


@pytest.mark.parametrize(
    ("types", "lids"),
    [
        (["Rubbish", "Food and Garden Organics"], ["red", "green"]),
        (["Recycling", "Glass recycling"], ["yellow", "purple"]),
        # "Garden Waste" must hit green before the red "waste" keyword
        (["Garden Waste", "General Waste", "Hard rubbish"], ["green", "red"]),
        (["Street sweeping"], []),
    ],
)
def test_lid_colours(types, lids):
    assert eng.lid_colours(types) == lids
