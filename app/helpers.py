"""Shared helpers for dates, weather display, frame payload."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import calendar as calendar_model
from app.models import photos as photos_model
from app.models import settings as settings_model
from app.models import weather as weather_model
from app.validation import normalize_hex_color, parse_bounded_int


def get_timezone() -> ZoneInfo:
    name = settings_model.get("weather_timezone", "America/New_York") or "America/New_York"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def today_local() -> date:
    return datetime.now(get_timezone()).date()


def rolling_week_dates(center: date | None = None) -> list[date]:
    """Five days with today near the start: yesterday … today+3."""
    center = center or today_local()
    return [center + timedelta(days=offset) for offset in range(-1, 4)]


def c_to_f(celsius: float | None) -> float | None:
    if celsius is None:
        return None
    return celsius * 9.0 / 5.0 + 32.0


def format_temp(celsius: float | None, unit: str) -> str | None:
    if celsius is None:
        return None
    if unit.upper() == "F":
        return str(int(round(c_to_f(celsius))))
    return str(int(round(celsius)))


def build_frame_payload() -> dict:
    unit = (settings_model.get("temperature_unit", "F") or "F").upper()
    days = rolling_week_dates()
    date_strs = [d.isoformat() for d in days]
    entries = calendar_model.list_for_dates(date_strs)
    weather_by_date = weather_model.get_for_dates(date_strs)
    photos = photos_model.list_active()

    entries_by_date: dict[str, list] = {d: [] for d in date_strs}
    for row in entries:
        entries_by_date[row["entry_date"]].append(
            {
                "id": row["id"],
                "person_id": row["person_id"],
                "person_name": row["person_name"],
                "person_color": normalize_hex_color(row["person_color"]),
                "entry_type": row["entry_type"],
                "text": row["text"],
            }
        )

    day_columns = []
    today = today_local()
    for d in days:
        key = d.isoformat()
        w = weather_by_date.get(key)
        weather = None
        if w is not None:
            weather = {
                "low": format_temp(w["low_c"], unit),
                "high": format_temp(w["high_c"], unit),
                "current": format_temp(w["current_c"], unit),
                "condition": w["condition"],
                "condition_label": w["condition_label"],
                "unit": unit,
            }
        day_columns.append(
            {
                "date": key,
                "weekday": d.strftime("%a").upper(),
                "month_day": f"{d.strftime('%B')} {d.day}",
                "is_today": d == today,
                "weather": weather,
                "entries": entries_by_date[key],
            }
        )

    interval = parse_bounded_int(
        settings_model.get("photo_interval_seconds", "30"),
        default=30,
        minimum=5,
        maximum=600,
    )
    poll = parse_bounded_int(
        settings_model.get("frame_poll_seconds", "60"),
        default=60,
        minimum=10,
        maximum=600,
    )

    return {
        "today": today.isoformat(),
        "days": day_columns,
        "photos": [
            {
                "id": p["id"],
                "url": f"/media/{p['filename']}",
            }
            for p in photos
        ],
        "photo_interval_seconds": interval,
        "frame_poll_seconds": poll,
        "temperature_unit": unit,
    }
