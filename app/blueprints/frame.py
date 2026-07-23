"""Kiosk frame routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from app.helpers import build_frame_payload

bp = Blueprint("frame", __name__)


@bp.get("/")
def index():
    payload = build_frame_payload()
    return render_template("frame.html", **payload)


@bp.get("/api/frame")
def api_frame():
    return jsonify(build_frame_payload())


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})
