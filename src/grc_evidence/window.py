"""The audit window as UTC bounds `[start 00:00:00Z, end+1 00:00:00Z)`, so the last day is never dropped."""

from datetime import UTC, date, datetime, time, timedelta

Bounds = tuple[datetime, datetime]


def utc_bounds(start: date, end: date) -> Bounds:
    """The window from `start` to `end`, both days included."""
    return datetime.combine(start, time(), UTC), datetime.combine(end + timedelta(days=1), time(), UTC)


def parse_ts(value: str) -> datetime:
    """An ISO 8601 timestamp with a zone (`Z` or an offset), in UTC. A timestamp with no zone is an error."""
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        raise ValueError(f"timestamp {value!r} has no time zone")
    return ts.astimezone(UTC)


def in_window(ts: datetime, bounds: Bounds) -> bool:
    return bounds[0] <= ts < bounds[1]


def near_boundary(ts: datetime, bounds: Bounds, hours: int = 8) -> bool:
    """Within `hours` of either bound: a reviewer in another time zone may date it on the other side."""
    return any(abs(ts - bound) <= timedelta(hours=hours) for bound in bounds)
