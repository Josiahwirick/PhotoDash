"""Serve stored photos from configured storage path."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, send_from_directory

from app.services.photo_pipeline import resolve_storage_path

bp = Blueprint("media", __name__)


@bp.get("/media/<path:filename>")
def media(filename: str):
    if "/" in filename or "\\" in filename or filename.startswith("."):
        abort(404)
    root = resolve_storage_path(current_app.config["STORAGE_PATH"])
    return send_from_directory(root, filename)
