from datetime import date, datetime, timedelta, timezone

import pytest

from solution import (
    AmbiguousTimeError,
    NonexistentTimeError,
    add_calendar_days,
    add_elapsed,
    day_length_hours,
    format_local,
    local_day_bounds,
    to_utc,
)

KYIV = "Europe/Kyiv"
NYC = "America/New_York"
UTC = timezone.utc


def utc(*args):
    return datetime(*args, tzinfo=UTC)


# --- to_utc: звичайний час -------------------------------------------------------------------

def test_winter_and_summer_offsets():
    assert to_utc(datetime(2026, 1, 15, 12, 0), KYIV) == utc(2026, 1, 15, 10, 0)  # EET, +02:00
    assert to_utc(datetime(2026, 7, 1, 12, 0), KYIV) == utc(2026, 7, 1, 9, 0)    # EEST, +03:00
    assert to_utc(datetime(2026, 7, 1, 12, 0), NYC) == utc(2026, 7, 1, 16, 0)    # EDT, -04:00


def test_result_is_aware_utc():
    r = to_utc(datetime(2026, 7, 1, 12, 0), KYIV)
    assert r.tzinfo is not None and r.utcoffset() == timedelta(0)


def test_aware_input_and_bad_policy_are_value_errors():
    with pytest.raises(ValueError):
        to_utc(datetime(2026, 7, 1, 12, 0, tzinfo=UTC), KYIV)
    with pytest.raises(ValueError):
        to_utc(datetime(2026, 7, 1, 12, 0), KYIV, ambiguous="whatever")


# --- to_utc: пропуск навесні -----------------------------------------------------------------

@pytest.mark.parametrize("minute", [0, 30, 59])
def test_spring_gap_is_nonexistent_kyiv(minute):
    with pytest.raises(NonexistentTimeError):
        to_utc(datetime(2026, 3, 29, 3, minute), KYIV)


def test_times_around_the_spring_gap_exist_kyiv():
    assert to_utc(datetime(2026, 3, 29, 2, 59), KYIV) == utc(2026, 3, 29, 0, 59)
    assert to_utc(datetime(2026, 3, 29, 4, 0), KYIV) == utc(2026, 3, 29, 1, 0)


def test_spring_gap_new_york():
    with pytest.raises(NonexistentTimeError):
        to_utc(datetime(2026, 3, 8, 2, 30), NYC)
    assert to_utc(datetime(2026, 3, 8, 3, 0), NYC) == utc(2026, 3, 8, 7, 0)


def test_nonexistent_error_is_value_error():
    assert issubclass(NonexistentTimeError, ValueError)
    assert issubclass(AmbiguousTimeError, ValueError)


# --- to_utc: дубль восени --------------------------------------------------------------------

def test_autumn_overlap_policies_kyiv():
    local = datetime(2026, 10, 25, 3, 30)
    with pytest.raises(AmbiguousTimeError):
        to_utc(local, KYIV)
    with pytest.raises(AmbiguousTimeError):
        to_utc(local, KYIV, ambiguous="raise")
    assert to_utc(local, KYIV, ambiguous="earlier") == utc(2026, 10, 25, 0, 30)  # EEST +03:00
    assert to_utc(local, KYIV, ambiguous="later") == utc(2026, 10, 25, 1, 30)    # EET +02:00


def test_autumn_overlap_new_york():
    local = datetime(2026, 11, 1, 1, 30)
    assert to_utc(local, NYC, "earlier") == utc(2026, 11, 1, 5, 30)  # EDT -04:00
    assert to_utc(local, NYC, "later") == utc(2026, 11, 1, 6, 30)    # EST -05:00


def test_times_around_the_autumn_overlap_are_not_ambiguous():
    assert to_utc(datetime(2026, 10, 25, 2, 59), KYIV) == utc(2026, 10, 24, 23, 59)
    assert to_utc(datetime(2026, 10, 25, 4, 0), KYIV) == utc(2026, 10, 25, 2, 0)


def test_policy_is_ignored_for_unambiguous_times():
    for policy in ("raise", "earlier", "later"):
        assert to_utc(datetime(2026, 6, 1, 10, 0), KYIV, policy) == utc(2026, 6, 1, 7, 0)


# --- add_calendar_days / add_elapsed ---------------------------------------------------------

def test_calendar_day_across_spring_forward_is_23_hours():
    start = utc(2026, 3, 28, 10, 0)  # 12:00 у Києві (EET)
    result = add_calendar_days(start, 1, KYIV)
    assert result == utc(2026, 3, 29, 9, 0)  # знову 12:00 у Києві, але вже EEST
    assert result - start == timedelta(hours=23)
    assert format_local(result, KYIV) == "2026-03-29T12:00+03:00"


def test_calendar_day_across_fall_back_is_25_hours():
    start = utc(2026, 10, 24, 9, 0)  # 12:00 у Києві (EEST)
    result = add_calendar_days(start, 1, KYIV)
    assert result == utc(2026, 10, 25, 10, 0)  # 12:00 у Києві (EET)
    assert result - start == timedelta(hours=25)


def test_calendar_days_normal_period_is_24_hours_per_day():
    start = utc(2026, 6, 1, 7, 0)
    assert add_calendar_days(start, 3, KYIV) - start == timedelta(hours=72)
    assert add_calendar_days(start, 0, KYIV) == start


def test_calendar_days_negative():
    start = utc(2026, 3, 29, 9, 0)  # 12:00 EEST
    assert add_calendar_days(start, -1, KYIV) == utc(2026, 3, 28, 10, 0)  # 12:00 EET


def test_calendar_days_landing_in_the_spring_gap_moves_forward():
    start = utc(2026, 3, 28, 1, 30)  # 03:30 у Києві (EET), доба до пропуску
    result = add_calendar_days(start, 1, KYIV)
    assert format_local(result, KYIV) == "2026-03-29T04:30+03:00"
    assert result == utc(2026, 3, 29, 1, 30)


def test_calendar_days_landing_in_the_autumn_overlap_takes_first_occurrence():
    start = utc(2026, 10, 24, 0, 30)  # 03:30 у Києві (EEST)
    result = add_calendar_days(start, 1, KYIV)
    assert result == utc(2026, 10, 25, 0, 30)
    assert format_local(result, KYIV) == "2026-10-25T03:30+03:00"


def test_calendar_days_requires_aware_utc():
    with pytest.raises(ValueError):
        add_calendar_days(datetime(2026, 3, 28, 10, 0), 1, KYIV)
    with pytest.raises(ValueError):
        add_calendar_days(datetime(2026, 3, 28, 10, 0, tzinfo=timezone(timedelta(hours=2))), 1, KYIV)


def test_add_elapsed_ignores_dst():
    start = utc(2026, 3, 28, 10, 0)
    result = add_elapsed(start, 24)
    assert result == utc(2026, 3, 29, 10, 0)
    assert format_local(result, KYIV) == "2026-03-29T13:00+03:00"  # локально 25 годин
    assert add_elapsed(start, 0.5) == utc(2026, 3, 28, 10, 30)
    assert add_elapsed(start, -2) == utc(2026, 3, 28, 8, 0)


def test_add_elapsed_requires_aware_utc():
    with pytest.raises(ValueError):
        add_elapsed(datetime(2026, 1, 1), 1)


# --- межі доби -------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "day, tz, hours",
    [
        (date(2026, 3, 29), KYIV, 23),
        (date(2026, 10, 25), KYIV, 25),
        (date(2026, 3, 28), KYIV, 24),
        (date(2026, 7, 1), KYIV, 24),
        (date(2026, 3, 8), NYC, 23),
        (date(2026, 11, 1), NYC, 25),
        (date(2026, 11, 2), NYC, 24),
        (date(2026, 3, 29), "UTC", 24),
    ],
)
def test_day_length(day, tz, hours):
    assert day_length_hours(day, tz) == hours


def test_day_bounds_values_kyiv_spring():
    start, end = local_day_bounds(date(2026, 3, 29), KYIV)
    assert start == utc(2026, 3, 28, 22, 0)  # північ у Києві (EET) = 22:00 UTC
    assert end == utc(2026, 3, 29, 21, 0)    # наступна північ уже EEST = 21:00 UTC
    assert start.utcoffset() == timedelta(0) and end.utcoffset() == timedelta(0)


def test_day_bounds_values_kyiv_autumn():
    start, end = local_day_bounds(date(2026, 10, 25), KYIV)
    assert start == utc(2026, 10, 24, 21, 0)
    assert end == utc(2026, 10, 25, 22, 0)


def test_consecutive_days_tile_without_gaps():
    day = date(2026, 3, 25)
    prev_end = None
    for _ in range(10):
        start, end = local_day_bounds(day, KYIV)
        if prev_end is not None:
            assert start == prev_end
        assert end > start
        prev_end = end
        day += timedelta(days=1)


# --- форматування ----------------------------------------------------------------------------

def test_format_local():
    assert format_local(utc(2026, 3, 29, 1, 30), KYIV) == "2026-03-29T04:30+03:00"
    assert format_local(utc(2026, 1, 1, 0, 0), KYIV) == "2026-01-01T02:00+02:00"
    assert format_local(utc(2026, 7, 1, 16, 5), NYC) == "2026-07-01T12:05-04:00"


def test_format_local_requires_aware_utc():
    with pytest.raises(ValueError):
        format_local(datetime(2026, 1, 1), KYIV)


def test_utc_roundtrip_through_local_for_every_hour_of_a_dst_day():
    base = utc(2026, 10, 24, 20, 0)
    seen = set()
    for h in range(0, 30):
        moment = add_elapsed(base, h)
        text = format_local(moment, KYIV)
        assert text not in seen  # з зсувом у рядку кожна мить унікальна, навіть у «подвійну» годину
        seen.add(text)
