"""Input validation and safe parsing for admin settings and uploads."""

from __future__ import annotations

import re
from pathlib import Path

from flask import current_app

from app.config import BASE_DIR
from app.models import settings as settings_model

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# ~12 MP — enough for a sharp frame strip without exhausting a 1GB Pi.
MAX_IMAGE_PIXELS = 12_000_000
MAX_IMAGE_DIMENSION = 8192


def parse_bounded_int(
    value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Parse an integer form value, falling back to default if invalid."""
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def normalize_hex_color(value: str | None) -> str | None:
    """Return a #RRGGBB color or None if empty/invalid."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if HEX_COLOR_RE.fullmatch(stripped):
        return stripped.lower()
    return None


def allowed_storage_roots(configured_fallback: Path) -> list[Path]:
    """Directories where photo storage may be configured."""
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path | str | None) -> None:
        if path is None:
            return
        try:
            resolved = Path(path).expanduser().resolve()
        except OSError:
            return
        key = str(resolved)
        if key in seen:
            return
        seen.add(key)
        roots.append(resolved)

    add(configured_fallback)
    add(current_app.config.get("FALLBACK_STORAGE_PATH"))
    add(current_app.config.get("STORAGE_PATH"))
    add(BASE_DIR / "data")
    configured = settings_model.get("storage_path") or ""
    if configured.strip():
        add(configured.strip())
    add("/var/lib/photodash")
    add("/mnt")
    if current_app.config.get("TESTING"):
        add("/tmp")

    return roots


def validate_storage_path_setting(value: str | None, configured_fallback: Path) -> tuple[str, str | None]:
    """
    Validate admin storage_path setting.

    Returns (normalized_value, error_message). Empty string clears custom path.
    """
    if value is None:
        return "", None
    stripped = value.strip()
    if not stripped:
        return "", None

    try:
        resolved = Path(stripped).expanduser().resolve()
    except OSError:
        return "", "Storage path is not valid."

    if not resolved.is_absolute():
        return "", "Storage path must be an absolute path."

    for root in allowed_storage_roots(configured_fallback):
        try:
            resolved.relative_to(root)
            return str(resolved), None
        except ValueError:
            continue

    return "", "Storage path must be under an allowed location (e.g. /mnt or /var/lib/photodash)."
