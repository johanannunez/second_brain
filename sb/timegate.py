"""Time-zone aware schedule gates for repeatable worker runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
PACIFIC = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class Schedule:
    frequency: Literal["daily", "weekly", "monthly"]
    target: time
    weekday: int | None = None  # Monday is 0.
    monthday: int | None = None
    timezone: ZoneInfo = CENTRAL


SCHEDULES = {
    "morning-briefing": Schedule("daily", time(5, 0)),
    "midday-sweep": Schedule("daily", time(12, 30)),
    "evening-check-in": Schedule("daily", time(21, 0)),
    "weekly-review": Schedule("weekly", time(18, 45), weekday=6),
    "monthly-close": Schedule("monthly", time(8, 0), monthday=1),
}


def briefing_date(now: datetime) -> date:
    """Brief date rolls at 3 PM Pacific, as specified by the worker brief."""
    pacific = localize(now, PACIFIC)
    return pacific.date() + (timedelta(days=1) if pacific.time() >= time(15, 0) else timedelta())


def localize(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(zone)


def is_due(
    schedule: Schedule,
    now: datetime,
    *,
    output_exists: bool,
) -> bool:
    """Run after the local target only, and at most once for the output date."""
    if output_exists:
        return False
    local_now = localize(now, schedule.timezone)
    if local_now.time().replace(tzinfo=None) <= schedule.target:
        return False
    if schedule.frequency == "daily":
        return True
    if schedule.frequency == "weekly":
        return local_now.weekday() == schedule.weekday
    return local_now.day == schedule.monthday


def run_metadata(now: datetime, source_failures: dict[str, str] | None = None) -> dict[str, object]:
    """Build the common timestamps and source-failure metadata for data.json."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    central = now.astimezone(CENTRAL)
    pacific = now.astimezone(PACIFIC)
    return {
        "now_utc": now.astimezone(UTC).isoformat(),
        "now_central": central.isoformat(),
        "now_pacific": pacific.isoformat(),
        "brief_date": briefing_date(now).isoformat(),
        "source_failures": dict(source_failures or {}),
    }


def cron_lines(schedule: Schedule) -> tuple[str, str]:
    """Return the two UTC cron entries for the schedule's CST and CDT targets."""
    candidates = []
    for offset in (timedelta(hours=-6), timedelta(hours=-5)):
        # Build representative standard/daylight local instants to map UTC cron.
        if schedule.frequency == "weekly":
            day = schedule.weekday
            local_date = date(2026, 1, 4)  # Sunday in standard time.
            local_date += timedelta(days=(day - local_date.weekday()) % 7)
        elif schedule.frequency == "monthly":
            local_date = date(2026, 1, schedule.monthday)
        else:
            local_date = date(2026, 1, 15)
        local_dt = datetime.combine(local_date, schedule.target)
        utc_dt = (local_dt - offset).replace(tzinfo=UTC)
        if schedule.frequency == "daily":
            candidates.append(f"7 {utc_dt.hour} * * *")
        elif schedule.frequency == "weekly":
            cron_weekday = (utc_dt.weekday() + 1) % 7  # GitHub cron: Sunday is 0.
            candidates.append(f"7 {utc_dt.hour} * * {cron_weekday}")
        else:
            candidates.append(f"7 {utc_dt.hour} {utc_dt.day} * *")
    return tuple(candidates)  # type: ignore[return-value]
