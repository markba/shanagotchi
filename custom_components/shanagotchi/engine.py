"""Dose, check-in, refill and mood rules. No Home Assistant imports, so it tests without a running instance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, time, timedelta

MOODS = ["hungry", "sleep", "ask", "sad", "low", "okay", "happy", "proud"]
STATUSES = ["waiting", "due", "taken", "skipped"]

ALERT = "alert"
CLEAR_DOSE = "clear_dose"
ASK_FEELING = "ask_feeling"
BAD_FEELING = "bad_feeling"
CLEAR_FEELING = "clear_feeling"
REFILL = "refill"
CLEAR_REFILL = "clear_refill"

CHECKIN_REASK = timedelta(hours=2)
REFILL_NOTIFY_HOUR = 10

# First match wins, so "Glass recycling" is purple and "Garden waste" is green
LID_KEYWORDS = {
    "purple": ("glass",),
    "yellow": ("recycl",),
    "green": ("food", "garden", "green", "fogo", "organic"),
    "red": ("rubbish", "garbage", "general", "landfill", "waste"),
}


def lid_colours(waste_types: list[str]) -> list[str]:
    """Map council waste type names to Australian standard lid colours."""
    lids = []
    for waste_type in waste_types:
        name = waste_type.lower()
        for lid, keywords in LID_KEYWORDS.items():
            if any(k in name for k in keywords):
                if lid not in lids:
                    lids.append(lid)
                break
    return lids


@dataclass(frozen=True)
class Settings:
    dose_times: tuple[time, ...]
    dose_window: timedelta
    early_window: timedelta
    repeat: timedelta
    max_repeats: int
    checkin_time: time
    sleep_start: time
    sleep_end: time
    refill_name: str
    refill_interval_days: int


@dataclass
class State:
    status: str = "waiting"
    status_changed: datetime | None = None
    # Scheduled time of the dose that is due now, None when nothing is due
    due_since: datetime | None = None
    last_reminder: datetime | None = None
    reminders_sent: int = 0
    # Latest dose time already taken or skipped early, so it doesn't fire again
    handled_until: datetime | None = None
    notice: str = ""
    taken_today: int = 0
    missed_today: int = 0
    streak_days: int = 0
    feeling: int = 0
    checkin_asks: int = 0
    last_checkin_ask: datetime | None = None
    refill_last_ordered: date | None = None
    refill_notified: date | None = None
    last_tick: datetime | None = None

    def as_dict(self) -> dict:
        return {
            k: v.isoformat() if isinstance(v, date) else v
            for k, v in asdict(self).items()
        }

    @classmethod
    def from_dict(cls, data: dict) -> State:
        state = cls()
        for f in fields(cls):
            value = data.get(f.name)
            if value is None:
                continue
            if f.name in _DATETIME_FIELDS:
                value = datetime.fromisoformat(value)
            elif f.name in _DATE_FIELDS:
                value = date.fromisoformat(value)
            setattr(state, f.name, value)
        return state


_DATETIME_FIELDS = {
    "status_changed",
    "due_since",
    "last_reminder",
    "handled_until",
    "last_checkin_ask",
    "last_tick",
}
_DATE_FIELDS = {"refill_last_ordered", "refill_notified"}


class Engine:
    """Every method takes the current local time and returns the notification events to send."""

    def __init__(self, settings: Settings, state: State) -> None:
        self.settings = settings
        self.state = state

    @property
    def dose_due(self) -> bool:
        return self.state.due_since is not None

    def checkin_pending(self, now: datetime) -> bool:
        return self.state.feeling == 0 and now.time() >= self.settings.checkin_time

    def refill_due(self, now: datetime) -> bool:
        last = self.state.refill_last_ordered
        return (
            bool(self.settings.refill_name)
            and last is not None
            and (now.date() - last).days >= self.settings.refill_interval_days
        )

    def next_dose(self, now: datetime) -> time:
        times = sorted(self.settings.dose_times)
        return next((t for t in times if t > now.time()), times[0])

    def mood(self, now: datetime) -> str:
        if self.dose_due:
            return "hungry"
        t, start, end = now.time(), self.settings.sleep_start, self.settings.sleep_end
        asleep = (t >= start or t < end) if start > end else (start <= t < end)
        if asleep:
            return "sleep"
        if self.checkin_pending(now):
            return "ask"
        score = self.state.feeling or 3
        if self.state.missed_today:
            score -= 2
        elif self.state.taken_today:
            score += 1
        return ["sad", "low", "okay", "happy", "proud"][max(1, min(score, 5)) - 1]

    def tick(self, now: datetime) -> list[str]:
        """Process everything that fell due since the last tick, including across a sleep or restart."""
        s = self.state
        last = s.last_tick or now - timedelta(minutes=1)
        s.last_tick = now
        events: list[str] = []
        # A dose that was due when its time was removed or moved in the settings
        if s.due_since and s.due_since.time() not in self.settings.dose_times:
            s.due_since = None
            s.status = "waiting"
            events.append(CLEAR_DOSE)
        was_due = s.due_since

        points: list[tuple[datetime, bool]] = []
        day = last.date()
        while day <= now.date():
            for t in self.settings.dose_times:
                points.append((datetime.combine(day, t, tzinfo=now.tzinfo), False))
            day += timedelta(days=1)
            points.append((datetime.combine(day, time(), tzinfo=now.tzinfo), True))

        first_midnight = True
        # At 00:00 the day rolls over before a midnight dose opens
        crossed = sorted(
            (p for p in points if last < p[0] <= now), key=lambda p: (p[0], not p[1])
        )
        for at, is_midnight in crossed:
            self._expire(at, events)
            if is_midnight:
                self._rollover(events, count_streak=first_midnight)
                first_midnight = False
            else:
                self._dose_falls_due(at, now, events)
        self._expire(now, events)

        if s.due_since and s.due_since != was_due:
            s.reminders_sent = 0
            s.last_reminder = now
            events.append(ALERT)
        elif (
            s.due_since
            and s.reminders_sent < self.settings.max_repeats
            and now - s.last_reminder >= self.settings.repeat
        ):
            s.reminders_sent += 1
            s.last_reminder = now
            events.append(ALERT)

        if self.checkin_pending(now) and (
            s.checkin_asks == 0
            or (s.checkin_asks == 1 and now - s.last_checkin_ask >= CHECKIN_REASK)
        ):
            s.checkin_asks += 1
            s.last_checkin_ask = now
            events.append(ASK_FEELING)

        if (
            self.refill_due(now)
            and now.hour >= REFILL_NOTIFY_HOUR
            and s.refill_notified != now.date()
        ):
            s.refill_notified = now.date()
            events.append(REFILL)
        return events

    def resolve(self, now: datetime, outcome: str) -> list[str]:
        """Mark the due dose taken or skipped, or an upcoming one inside the early window."""
        s = self.state
        if not self.dose_due:
            early = next(
                (
                    at
                    for at in sorted(
                        datetime.combine(day, t, tzinfo=now.tzinfo)
                        for day in (now.date(), now.date() + timedelta(days=1))
                        for t in self.settings.dose_times
                    )
                    if (s.handled_until is None or at > s.handled_until)
                    and timedelta() <= at - now <= self.settings.early_window
                ),
                None,
            )
            if early is None:
                return []
            s.handled_until = early
        else:
            # So a replay of this dose time after a crash can't make it due again
            s.handled_until = s.due_since
        s.status = outcome
        s.status_changed = now
        if outcome == "taken":
            s.taken_today += 1
        s.due_since = None
        s.notice = ""
        return [CLEAR_DOSE]

    def set_feeling(self, value: int) -> list[str]:
        if not 1 <= value <= 5:
            return [BAD_FEELING]
        self.state.feeling = value
        return [CLEAR_FEELING]

    def refill_ordered(self, now: datetime) -> list[str]:
        self.state.refill_last_ordered = now.date()
        return [CLEAR_REFILL]

    def _dose_falls_due(self, at: datetime, now: datetime, events: list[str]) -> None:
        s = self.state
        if s.handled_until is not None and at <= s.handled_until:
            return
        # The same time can come round twice, at the end of daylight saving or with two doses set alike
        if s.due_since == at:
            return
        # A window that opened and closed while HA wasn't running can't be judged either way
        if at + self.settings.dose_window <= now:
            return
        if s.due_since:
            self._miss(events)
        s.due_since = at
        s.status = "due"
        s.status_changed = at

    def _expire(self, at: datetime, events: list[str]) -> None:
        due = self.state.due_since
        if due and at >= due + self.settings.dose_window:
            self._miss(events)

    def _miss(self, events: list[str]) -> None:
        s = self.state
        s.missed_today += 1
        s.notice = f"Missed {s.due_since:%H:%M} dose"
        s.due_since = None
        s.status = "waiting"
        events.append(CLEAR_DOSE)

    def _rollover(self, events: list[str], count_streak: bool) -> None:
        s = self.state
        if s.due_since:
            self._miss(events)
        # Only the day HA saw end counts. Further midnights crossed while it was off are unknown
        if count_streak:
            s.streak_days = 0 if s.missed_today else s.streak_days + 1
        s.status = "waiting"
        s.taken_today = 0
        s.missed_today = 0
        s.feeling = 0
        s.checkin_asks = 0
