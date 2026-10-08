"""Pure daily occurrence rules; no dispatch or clock reads."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class DueOccurrence:
    key: str
    local_date: date
    scheduled_for: datetime


def daily_instant(day: date, zone_name: str, hour: int, minute: int) -> datetime | None:
    """Use the first fold on fallback days; skip a nonexistent spring wall time."""
    zone = ZoneInfo(zone_name)
    wall = datetime.combine(day, time(hour, minute)).replace(tzinfo=zone, fold=0)
    instant = wall.astimezone(timezone.utc)
    if instant.astimezone(zone).replace(tzinfo=None) != wall.replace(tzinfo=None):
        return None
    return instant


def latest_due(schedule_id: str, zone_name: str, hour: int, minute: int,
               *, after: datetime, now: datetime) -> DueOccurrence | None:
    """Coalesce due runs to the latest one inside a bounded 24-hour window."""
    if after.tzinfo is None or now.tzinfo is None:
        raise ValueError('Schedule timestamps must be timezone-aware')
    current = now.astimezone(timezone.utc)
    lower = max(after.astimezone(timezone.utc), current - timedelta(hours=24))
    day = current.astimezone(ZoneInfo(zone_name)).date()
    for offset in range(3):
        local_day = day - timedelta(days=offset)
        instant = daily_instant(local_day, zone_name, hour, minute)
        if instant is not None and lower < instant <= current:
            return DueOccurrence(f'{schedule_id}:{local_day.isoformat()}', local_day, instant)
    return None
