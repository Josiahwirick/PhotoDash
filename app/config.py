"""Application configuration from environment and sensible Pi defaults."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _env(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    return value


def load_config() -> dict:
    """Read configuration from the current environment."""
    return {
        "SECRET_KEY": _env("SECRET_KEY", "dev-insecure-change-me"),
        "DB_PATH": Path(
            _env("PHOTODASH_DB_PATH", str(BASE_DIR / "data" / "photodash.db"))
        ),
        "STORAGE_PATH": Path(
            _env("PHOTODASH_STORAGE_PATH", str(BASE_DIR / "data" / "photos"))
        ),
        "FALLBACK_STORAGE_PATH": Path(
            _env(
                "PHOTODASH_FALLBACK_STORAGE_PATH",
                str(BASE_DIR / "data" / "photos"),
            )
        ),
        "HOST": _env("PHOTODASH_HOST", "0.0.0.0"),
        "PORT": int(_env("PHOTODASH_PORT", "8080") or "8080"),
        "BOOTSTRAP_PASSWORD": _env("PHOTODASH_PASSWORD", "photodash"),
        "WEATHER_INTERVAL_MINUTES": int(
            _env("PHOTODASH_WEATHER_INTERVAL_MINUTES", "30") or "30"
        ),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "MAX_CONTENT_LENGTH": 32 * 1024 * 1024,
        "TESTING": _env("PHOTODASH_TESTING", "0") == "1",
    }


# Back-compat alias used in type hints / docs
class Config:
    """Legacy class; prefer load_config() so env is read at app creation."""

    @staticmethod
    def as_dict() -> dict:
        return load_config()


DEFAULT_SETTINGS = {
    "photo_interval_seconds": "30",
    "storage_path": "",
    "weather_latitude": "",
    "weather_longitude": "",
    "weather_timezone": "America/New_York",
    "temperature_unit": "F",
    "frame_poll_seconds": "60",
}
