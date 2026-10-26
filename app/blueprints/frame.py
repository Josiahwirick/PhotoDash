"""Kiosk frame routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from app.helpers import build_frame_payload
from app.services import kiosk_heartbeat

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


@bp.post("/api/kiosk-heartbeat")
def kiosk_heartbeat_ping():
    """Frame JS pings this so the watchdog can detect a frozen Chromium renderer.

    Only accepted from localhost (the Pi kiosk). LAN browsers viewing the frame
    must not keep the heartbeat alive when the kiosk itself is dead.

    JSON body::
        {"dom_ok": true, "raf_seq": 123, "photo_tick": 4}

    ``raf_seq`` must advance over time (requestAnimationFrame). A frozen main
    thread stops it; the watchdog treats a stuck sequence as a freeze even if
    timers still fire.
    """
    addr = (request.remote_addr or "").strip()
    if addr not in ("127.0.0.1", "::1"):
        return jsonify({"ok": False, "error": "localhost only"}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    dom_ok = bool(payload.get("dom_ok", True))
    try:
        raf_seq = int(payload.get("raf_seq") or 0)
    except (TypeError, ValueError):
        raf_seq = 0
    try:
        photo_tick = int(payload.get("photo_tick") or 0)
    except (TypeError, ValueError):
        photo_tick = 0
    path = kiosk_heartbeat.touch_heartbeat(
        dom_ok=dom_ok,
        raf_seq=raf_seq,
        photo_tick=photo_tick,
    )
    return jsonify(
        {
            "ok": True,
            "dom_ok": dom_ok,
            "raf_seq": raf_seq,
            "photo_tick": photo_tick,
            "path": str(path),
        }
    )
