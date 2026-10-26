from datetime import datetime

import pytest

from sb.timegate import SCHEDULES, briefing_date, cron_lines, is_due


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_daily_gate_waits_for_target_and_skips_existing_output():
    schedule = SCHEDULES["morning-briefing"]
    assert not is_due(schedule, dt("2026-10-26T10:00:00+00:00"), output_exists=False)
    assert is_due(schedule, dt("2026-10-26T10:07:00+00:00"), output_exists=False)
    assert not is_due(schedule, dt("2026-10-26T11:07:00+00:00"), output_exists=True)


def test_weekly_and_monthly_gates_use_local_calendar():
    sunday_after_target = dt("2026-10-25T23:50:00+00:00")  # 6:50 PM CDT Sunday.
    monday_central = dt("2026-10-26T05:00:00+00:00")
    assert is_due(SCHEDULES["weekly-review"], sunday_after_target, output_exists=False)
    assert not is_due(SCHEDULES["weekly-review"], monday_central, output_exists=False)
    assert is_due(SCHEDULES["monthly-close"], dt("2026-11-01T14:07:00+00:00"), output_exists=False)
    assert not is_due(
        SCHEDULES["monthly-close"], dt("2026-11-02T14:07:00+00:00"), output_exists=False
    )


def test_briefing_date_rolls_at_three_pm_pacific_and_requires_aware_datetime():
    assert briefing_date(dt("2026-10-26T21:59:00+00:00")).isoformat() == "2026-10-26"
    assert briefing_date(dt("2026-10-26T22:00:00+00:00")).isoformat() == "2026-10-27"
    with pytest.raises(ValueError, match="timezone-aware"):
        briefing_date(datetime(2026, 10, 26))


def test_cron_lines_cover_cst_and_cdt_at_off_minute():
    assert cron_lines(SCHEDULES["morning-briefing"]) == ("7 11 * * *", "7 10 * * *")
    assert cron_lines(SCHEDULES["weekly-review"]) == ("7 0 * * 1", "7 23 * * 0")
    assert cron_lines(SCHEDULES["monthly-close"]) == ("7 14 1 * *", "7 13 1 * *")
