"""The audit window: UTC bounds that keep the last day, and the near-boundary flag."""

from datetime import UTC, date, datetime

import pytest

from grc_evidence.window import in_window, near_boundary, parse_ts, utc_bounds


def test_bounds_include_last_day() -> None:
    lo, hi = utc_bounds(date(2026, 6, 1), date(2026, 8, 31))
    assert lo == datetime(2026, 6, 1, tzinfo=UTC) and hi == datetime(2026, 9, 1, tzinfo=UTC)
    assert in_window(parse_ts("2026-08-31T23:59:59Z"), (lo, hi))
    assert not in_window(parse_ts("2026-09-01T00:00:00Z"), (lo, hi))
    assert in_window(parse_ts("2026-06-01T00:00:00Z"), (lo, hi))
    assert not in_window(parse_ts("2026-05-31T23:59:59Z"), (lo, hi))


def test_near_boundary_eight_hours() -> None:
    b = utc_bounds(date(2026, 6, 1), date(2026, 8, 31))
    assert near_boundary(parse_ts("2026-08-31T16:00:00Z"), b)
    assert not near_boundary(parse_ts("2026-08-31T15:59:59Z"), b)
    assert near_boundary(parse_ts("2026-06-01T08:00:00Z"), b)
    assert not near_boundary(parse_ts("2026-06-01T08:00:01Z"), b)


def test_parse_ts_accepts_z_and_offset_and_returns_utc() -> None:
    assert parse_ts("2026-08-31T10:00:00Z") == parse_ts("2026-08-31T10:00:00+00:00")
    assert parse_ts("2026-08-31T12:00:00+02:00") == datetime(2026, 8, 31, 10, tzinfo=UTC)
    assert parse_ts("2026-08-31T12:00:00+02:00").tzinfo is UTC


def test_parse_ts_rejects_naive() -> None:
    with pytest.raises(ValueError):
        parse_ts("2026-08-31T10:00:00")
