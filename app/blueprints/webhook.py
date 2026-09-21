"""Shared-secret webhook for creating people and calendar entries."""

from __future__ import annotations

import os
import secrets
from typing import Any

from flask import Blueprint, jsonify, request
from sqlite3 import IntegrityError

from app.helpers import today_local
from app.models import calendar as calendar_model
from app.models import people as people_model
from app.models import settings as settings_model
from app.services.cliamp_control import stream_control
from app.services.intent_parser import merge_structured

bp = Blueprint("webhook", __name__)


def get_webhook_token() -> str:
    """Return the active webhook token (env override wins)."""
    env = (os.environ.get("PHOTODASH_WEBHOOK_TOKEN") or "").strip()
    if env:
        return env
    stored = settings_model.get("webhook_token") or ""
    return stored.strip()


def ensure_webhook_token() -> str:
    """Generate and persist a webhook token if missing (unless env override)."""
    env = (os.environ.get("PHOTODASH_WEBHOOK_TOKEN") or "").strip()
    if env:
        return env
    existing = (settings_model.get("webhook_token") or "").strip()
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    settings_model.set("webhook_token", token)
    return token


def regenerate_webhook_token() -> str:
    """Replace the stored webhook token (env override unchanged)."""
    token = secrets.token_urlsafe(32)
    settings_model.set("webhook_token", token)
    return token


def _extract_request_token() -> str:
    header = request.headers.get("X-PhotoDash-Token") or ""
    if header.strip():
        return header.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _token_ok(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)


@bp.post("/api/webhook")
def webhook():
    expected = get_webhook_token()
    if not expected or not _token_ok(_extract_request_token(), expected):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "JSON body required."}), 400

    parsed = merge_structured(payload, today=today_local())
    if parsed.error or not parsed.action:
        return jsonify({"ok": False, "error": parsed.error or "Invalid request."}), 400

    try:
        if parsed.action == "create_person":
            result = _create_person(parsed.fields)
            return jsonify({"ok": True, "action": "create_person", "result": result}), 200
        if parsed.action == "create_entry":
            result = _create_entry(parsed.fields)
            return jsonify({"ok": True, "action": "create_entry", "result": result}), 200
        if parsed.action == "stream_control":
            result = stream_control(str(parsed.fields.get("command") or ""))
            return jsonify({"ok": True, "action": "stream_control", "result": result}), 200
    except IntegrityError:
        return jsonify({"ok": False, "error": "A person with that name already exists."}), 409
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": False, "error": "Unsupported action."}), 400


def _create_person(fields: dict[str, Any]) -> dict[str, Any]:
    person_id = people_model.create_person(
        name=fields["name"],
        color=fields.get("color"),
    )
    row = people_model.get_person(person_id)
    return {
        "id": person_id,
        "name": row["name"] if row else fields["name"],
        "color": row["color"] if row else fields.get("color"),
    }


def _create_entry(fields: dict[str, Any]) -> dict[str, Any]:
    person_id = None
    person_name = fields.get("person")
    if person_name:
        row = people_model.get_person_by_name(str(person_name))
        if row is None:
            raise ValueError(f"No person named '{person_name}'. Add them first.")
        person_id = int(row["id"])
        person_name = row["name"]

    entry_id = calendar_model.create_entry(
        entry_date=fields["entry_date"],
        entry_type=fields["entry_type"],
        text=fields["text"],
        person_id=person_id,
    )
    return {
        "id": entry_id,
        "entry_date": fields["entry_date"],
        "entry_type": fields["entry_type"],
        "text": fields["text"],
        "person_id": person_id,
        "person_name": person_name,
    }
