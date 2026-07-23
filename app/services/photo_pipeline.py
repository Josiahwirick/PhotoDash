"""Photo upload processing: EXIF orient, rotate landscape 90° CW, store JPEG."""

from __future__ import annotations

import logging
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from werkzeug.datastructures import FileStorage

from app.models import photos as photos_model
from app.models import settings as settings_model

logger = logging.getLogger(__name__)

JPEG_QUALITY = 85


def resolve_storage_path(configured_fallback: Path) -> Path:
    """Return writable photo storage path; fall back if configured path missing."""
    configured = settings_model.get("storage_path") or ""
    candidates: list[Path] = []
    if configured.strip():
        candidates.append(Path(configured.strip()))
    candidates.append(Path(configured_fallback))

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".photodash_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError as exc:
            logger.warning("Storage path %s not usable: %s", path, exc)
    # Last resort: relative data dir under cwd
    fallback = Path("data") / "photos"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def process_and_store(file: FileStorage, storage_root: Path) -> int:
    """Process uploaded image and insert DB row. Returns photo id."""
    original_name = file.filename or "upload.jpg"
    raw = file.read()
    image = Image.open(BytesIO(raw))
    image = ImageOps.exif_transpose(image)

    # Normalize to RGB for JPEG
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")

    rotation_degrees = 0
    rotated = False
    width, height = image.size
    if width > height:
        # Landscape → rotate 90° clockwise so it fills the vertical photo strip.
        image = image.transpose(Image.Transpose.ROTATE_270)  # 90° CW
        rotation_degrees = 90
        rotated = True
        width, height = image.size

    filename = f"{uuid.uuid4().hex}.jpg"
    dest = storage_root / filename
    image.save(dest, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    return photos_model.create_photo(
        filename=filename,
        original_name=original_name,
        width=width,
        height=height,
        rotated=rotated,
        rotation_degrees=rotation_degrees,
        mime_type="image/jpeg",
    )


def delete_stored_file(filename: str, storage_root: Path) -> None:
    path = storage_root / filename
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete %s: %s", path, exc)
