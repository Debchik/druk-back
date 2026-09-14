from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo


def calendar_day_bounds_for_date(
    tz: str | ZoneInfo,
    day: date,
) -> tuple[datetime, datetime]:
    """Начало и конец календарного дня ``day`` в зоне ``tz`` (для запроса выписки)."""
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    start = datetime.combine(day, time(0, 0, 0), tzinfo=zone)
    end = datetime.combine(day, time(23, 59, 59), tzinfo=zone)
    return start, end


def today_calendar_day_bounds(tz: str | ZoneInfo) -> tuple[datetime, datetime]:
    """Текущие календарные сутки в зоне ``tz`` (00:00–23:59:59)."""
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    return calendar_day_bounds_for_date(zone, datetime.now(zone).date())


def previous_calendar_day_bounds(tz: str | ZoneInfo) -> tuple[datetime, datetime]:
    """Предыдущие календарные сутки в зоне ``tz`` (для ручной догрузки за прошлый день)."""
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    prev = datetime.now(zone).date() - timedelta(days=1)
    return calendar_day_bounds_for_date(zone, prev)


def today_and_yesterday_calendar_day_bounds(
    tz: str | ZoneInfo,
) -> tuple[datetime, datetime]:
    """Вчера 00:00 — сегодня 23:59:59 в зоне ``tz`` (для обновления loan_fact)."""
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    today = datetime.now(zone).date()
    yesterday = today - timedelta(days=1)
    from_dt, _ = calendar_day_bounds_for_date(zone, yesterday)
    _, to_dt = calendar_day_bounds_for_date(zone, today)
    return from_dt, to_dt
