"""Open-Meteo weather fetch and cache update."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from app.models import settings as settings_model
from app.models import weather as weather_model

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → (condition key, short label)
WMO_MAP = {
    0: ("clear", "Sunny"),
    1: ("clear", "Mostly clear"),
    2: ("cloudy", "Partly cloudy"),
    3: ("cloudy", "Cloudy"),
    45: ("fog", "Fog"),
    48: ("fog", "Fog"),
    51: ("rain", "Drizzle"),
    53: ("rain", "Drizzle"),
    55: ("rain", "Drizzle"),
    61: ("rain", "Rain"),
    63: ("rain", "Rain"),
    65: ("rain", "Heavy rain"),
    66: ("rain", "Freezing rain"),
    67: ("rain", "Freezing rain"),
    71: ("snow", "Snow"),
    73: ("snow", "Snow"),
    75: ("snow", "Heavy snow"),
    77: ("snow", "Snow"),
    80: ("rain", "Showers"),
    81: ("rain", "Showers"),
    82: ("rain", "Heavy showers"),
    85: ("snow", "Snow showers"),
    86: ("snow", "Snow showers"),
    95: ("thunder", "Thunder"),
    96: ("thunder", "Thunder"),
    99: ("thunder", "Thunder"),
}


def map_wmo(code: int | None) -> tuple[str, str]:
    if code is None:
        return "unknown", "—"
    return WMO_MAP.get(int(code), ("unknown", "—"))


def fetch_and_cache() -> bool:
    """Pull forecast for configured location into weather_cache. Returns True on success."""
    lat = settings_model.get("weather_latitude", "").strip()
    lon = settings_model.get("weather_longitude", "").strip()
    tz = settings_model.get("weather_timezone", "America/New_York").strip() or "America/New_York"

    if not lat or not lon:
        logger.info("Weather skipped: latitude/longitude not configured")
        return False

    try:
        latitude = float(lat)
        longitude = float(lon)
    except ValueError:
        logger.warning("Invalid weather coordinates: %s, %s", lat, lon)
        return False

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": tz,
        "temperature_unit": "celsius",
        "current": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "forecast_days": 7,
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        return False

    return _write_cache(data)


def _write_cache(data: dict[str, Any]) -> bool:
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    current = data.get("current") or {}
    current_temp = current.get("temperature_2m")
    current_code = current.get("weather_code")
    today = (data.get("daily") or {}).get("time", [None])[0]

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for i, forecast_date in enumerate(dates):
        high = highs[i] if i < len(highs) else None
        low = lows[i] if i < len(lows) else None
        code = codes[i] if i < len(codes) else None
        # Prefer current conditions for today.
        if forecast_date == today and current_code is not None:
            condition, label = map_wmo(current_code)
            cur = current_temp
        else:
            condition, label = map_wmo(code)
            cur = None if forecast_date != today else current_temp

        weather_model.upsert_day(
            forecast_date=forecast_date,
            low_c=low,
            high_c=high,
            current_c=cur,
            condition=condition,
            condition_label=label,
            fetched_at=fetched_at,
        )

    logger.info("Weather cache updated for %d day(s)", len(dates))
    return True
