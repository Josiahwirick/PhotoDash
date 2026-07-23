"""Weather cache access."""

from __future__ import annotations

from sqlite3 import Row

from app.db import get_db


def get_for_dates(dates: list[str]) -> dict[str, Row]:
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    rows = get_db().execute(
        f"SELECT * FROM weather_cache WHERE forecast_date IN ({placeholders})",
        dates,
    ).fetchall()
    return {row["forecast_date"]: row for row in rows}


def upsert_day(
    *,
    forecast_date: str,
    low_c: float | None,
    high_c: float | None,
    current_c: float | None,
    condition: str,
    condition_label: str,
    fetched_at: str,
) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO weather_cache
          (forecast_date, low_c, high_c, current_c, condition, condition_label, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(forecast_date) DO UPDATE SET
          low_c = excluded.low_c,
          high_c = excluded.high_c,
          current_c = excluded.current_c,
          condition = excluded.condition,
          condition_label = excluded.condition_label,
          fetched_at = excluded.fetched_at,
          source = 'open-meteo'
        """,
        (
            forecast_date,
            low_c,
            high_c,
            current_c,
            condition,
            condition_label,
            fetched_at,
        ),
    )
    db.commit()
