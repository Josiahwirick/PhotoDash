"""Serve stored photos from configured storage path."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, request, send_from_directory

from app.services.photo_pipeline import ensure_frame_variant, resolve_storage_path
from app.validation import is_safe_stored_filename

bp = Blueprint("media", __name__)


@bp.get("/media/<path:filename>")
def media(filename: str):
    if not is_safe_stored_filename(filename):
        abort(404)
    root = resolve_storage_path(current_app.config["STORAGE_PATH"])
    size = (request.args.get("size") or "").strip().lower()
    if size == "frame":
        try:
            variant = ensure_frame_variant(root, filename)
        except (OSError, ValueError):
            abort(404)
        return send_from_directory(root, variant.name, max_age=86400)
    return send_from_directory(root, filename)
