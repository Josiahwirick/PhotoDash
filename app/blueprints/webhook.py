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
from app.services.reset_control import reset_frame

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
        if parsed.action == "list_entries":
            result = _list_entries(parsed.fields)
            return jsonify({"ok": True, "action": "list_entries", "result": result}), 200
        if parsed.action == "delete_entry":
            result = _delete_entry(parsed.fields)
            return jsonify({"ok": True, "action": "delete_entry", "result": result}), 200
        if parsed.action == "stream_control":
            result = stream_control(str(parsed.fields.get("command") or ""))
            return jsonify({"ok": True, "action": "stream_control", "result": result}), 200
        if parsed.action == "reset_frame":
            result = reset_frame(scope=str(parsed.fields.get("scope") or "all"))
            return jsonify({"ok": True, "action": "reset_frame", "result": result}), 200
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


def _entry_summary(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "entry_date": row["entry_date"],
        "entry_type": row["entry_type"],
        "text": row["text"],
        "person_name": row["person_name"],
    }


def _list_entries(fields: dict[str, Any]) -> dict[str, Any]:
    entry_date = (fields.get("entry_date") or "").strip()
    if not entry_date:
        raise ValueError("entry_date is required to list events.")
    rows = calendar_model.find_entries(entry_date=entry_date, limit=50)
    return {
        "entry_date": entry_date,
        "entries": [_entry_summary(row) for row in rows],
    }


def _delete_entry(fields: dict[str, Any]) -> dict[str, Any]:
    entry_ids_raw = fields.get("entry_ids")
    if entry_ids_raw is not None:
        deleted_rows = []
        missing: list[int] = []
        for raw_id in entry_ids_raw:
            eid = int(raw_id)
            row = calendar_model.get_entry(eid)
            if row is None:
                missing.append(eid)
                continue
            if calendar_model.delete_entry(eid):
                deleted_rows.append(_entry_summary(row))
        if not deleted_rows:
            if missing:
                raise ValueError(f"No calendar entries found for ids {missing}.")
            raise ValueError("No calendar entries deleted.")
        return {"deleted": len(deleted_rows), "entries": deleted_rows, "missing": missing}

    entry_id = fields.get("entry_id")
    if entry_id is not None:
        row = calendar_model.get_entry(int(entry_id))
        if row is None:
            raise ValueError(f"No calendar entry with id {entry_id}.")
        calendar_model.delete_entry(int(entry_id))
        return {
            "deleted": 1,
            "entries": [_entry_summary(row)],
        }

    person_id = None
    person_name = fields.get("person")
    if person_name:
        prow = people_model.get_person_by_name(str(person_name))
        if prow is None:
            raise ValueError(f"No person named '{person_name}'.")
        person_id = int(prow["id"])

    text_query = (fields.get("text") or "").strip() or None
    entry_date = (fields.get("entry_date") or "").strip() or None
    entry_type = (fields.get("entry_type") or "").strip() or None
    if entry_type and entry_type not in ("chore", "appointment", "reminder"):
        entry_type = None

    if not entry_date and not text_query and person_id is None and not entry_type:
        raise ValueError("Need an entry id, date, or text to delete.")

    matches = calendar_model.find_entries(
        entry_date=entry_date,
        entry_type=entry_type,
        text_query=text_query,
        person_id=person_id,
        from_date=None if entry_date else today_local().isoformat(),
        limit=20,
    )
    if not matches:
        raise ValueError("No matching calendar entry found.")
    if len(matches) > 1 and not (entry_date and text_query):
        # Ambiguous — ask for more detail rather than deleting several.
        preview = "; ".join(
            f"#{r['id']} {r['entry_date']} {r['entry_type']}: {r['text']}" for r in matches[:5]
        )
        raise ValueError(
            f"Matched {len(matches)} entries — be more specific (include date and text). "
            f"Matches: {preview}"
        )

    deleted_rows = []
    for row in matches:
        if calendar_model.delete_entry(int(row["id"])):
            deleted_rows.append(_entry_summary(row))
    if not deleted_rows:
        raise ValueError("No matching calendar entry found.")
    return {"deleted": len(deleted_rows), "entries": deleted_rows}
