"""Deterministic free-text intent parsing for webhook / Discord messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.helpers import today_local
from app.validation import normalize_hex_color

ENTRY_TYPES = ("chore", "appointment", "reminder")
MAX_TEXT_LEN = 200
MAX_NAME_LEN = 80

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_COLOR = re.compile(r"#([0-9A-Fa-f]{6})\b")
_PERSON_CMD = re.compile(
    r"^\s*(?:add|new|create)\s+person\s+(.+?)\s*$",
    re.IGNORECASE,
)
_TYPE_PREFIX = re.compile(
    r"^\s*(chore|appointment|reminder)\b\s*[:\-]?\s*(.+)$",
    re.IGNORECASE,
)
_FOR_PERSON = re.compile(r"\s+for\s+(.+?)\s*$", re.IGNORECASE)
_STREAM_STOP = re.compile(
    r"^\s*(?:stop|pause)\s+(?:the\s+)?(?:stream|lofi|music|radio)\s*$"
    r"|^\s*(?:stop|pause)\s+lofi(?:\s+stream)?\s*$"
    r"|^\s*lofi\s+off\s*$",
    re.IGNORECASE,
)
_STREAM_START = re.compile(
    r"^\s*(?:start|resume|play)\s+(?:the\s+)?(?:stream|lofi|music|radio)\s*$"
    r"|^\s*(?:start|resume|play)\s+lofi(?:\s+stream)?\s*$"
    r"|^\s*lofi\s+on\s*$",
    re.IGNORECASE,
)
_DELETE_ENTRY = re.compile(
    r"^\s*(?:delete|remove|cancel)\s+(?:(?:calendar\s+)?entry\s+)?(.+?)\s*$",
    re.IGNORECASE,
)
_DELETE_ENTRY_ID = re.compile(
    r"^\s*(?:delete|remove)\s+(?:entry\s+)?#?(\d+)\s*$",
    re.IGNORECASE,
)
# "cancel event on Friday" / "cancel on 2026-09-27" / "list events for Monday"
_LIST_ENTRIES = re.compile(
    r"^\s*(?:"
    r"(?:cancel|remove)\s+(?:(?:an?\s+)?(?:events?|entr(?:y|ies)|items?)\s+)?(?:on|for)\s+(.+?)"
    r"|list\s+(?:events?|entr(?:y|ies)|calendar)\s+(?:on|for)\s+(.+?)"
    r")\s*$",
    re.IGNORECASE,
)
_RESET_FRAME = re.compile(
    r"^\s*(?:reset|restart)\s+(?:the\s+)?(?:frame|photodash|kiosk|pi)\s*$"
    r"|^\s*(?:reset|restart)\s+(?:lofi|stream)\s*$"
    r"|^\s*photodash\s+reset\s*$",
    re.IGNORECASE,
)
_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


@dataclass
class ParsedIntent:
    """Structured result of parsing free text or merging structured fields."""

    action: str  # create_person | create_entry | delete_entry | list_entries | stream_control | reset_frame
    fields: dict[str, Any]
    error: str | None = None


def parse_text(text: str, *, today: date | None = None) -> ParsedIntent:
    """Parse free-text into a person, calendar, stream, or reset intent."""
    raw = (text or "").strip()
    if not raw:
        return ParsedIntent(action="", fields={}, error="Empty message.")

    reset = _parse_reset(raw)
    if reset is not None:
        return reset

    stream = _parse_stream(raw)
    if stream is not None:
        return stream

    listed = _parse_list_entries(raw, today=today or today_local())
    if listed is not None:
        return listed

    deleted = _parse_delete(raw, today=today or today_local())
    if deleted is not None:
        return deleted

    person = _parse_person(raw)
    if person is not None:
        return person

    calendar = _parse_calendar(raw, today=today or today_local())
    if calendar is not None:
        return calendar

    return ParsedIntent(
        action="",
        fields={},
        error=(
            "Could not understand that. Try: "
            "'add person Name', "
            "'chore tomorrow: take out trash for Estelle', "
            "'cancel event on Friday', "
            "'stop stream', or 'reset frame'."
        ),
    )


def _parse_list_entries(raw: str, *, today: date) -> ParsedIntent | None:
    """List calendar entries for a day (Discord cancel picker)."""
    match = _LIST_ENTRIES.match(raw)
    if not match:
        return None
    date_body = (match.group(1) or match.group(2) or "").strip()
    if not date_body:
        return ParsedIntent(
            action="list_entries",
            fields={},
            error="Say a day or date, e.g. 'cancel event on Friday'.",
        )
    entry_date, remainder = _consume_date(date_body, today=today)
    if entry_date is None or remainder.strip():
        return ParsedIntent(
            action="list_entries",
            fields={},
            error="Could not find a date (try today, tomorrow, Friday, or YYYY-MM-DD).",
        )
    return ParsedIntent(
        action="list_entries",
        fields={"entry_date": entry_date.isoformat()},
    )


def _parse_delete(raw: str, *, today: date) -> ParsedIntent | None:
    id_match = _DELETE_ENTRY_ID.match(raw)
    if id_match:
        return ParsedIntent(
            action="delete_entry",
            fields={"entry_id": int(id_match.group(1))},
        )

    match = _DELETE_ENTRY.match(raw)
    if not match:
        return None
    body = match.group(1).strip()
    if not body:
        return ParsedIntent(
            action="delete_entry",
            fields={},
            error="Say what to delete, e.g. 'delete chore tomorrow: take out trash'.",
        )

    # Reuse calendar parsing on the remainder when it looks like an entry phrase.
    calendar = _parse_calendar(body, today=today)
    if calendar is not None:
        if calendar.error:
            return ParsedIntent(action="delete_entry", fields={}, error=calendar.error)
        fields = dict(calendar.fields)
        return ParsedIntent(action="delete_entry", fields=fields)

    # Fallback: free-text match against upcoming entries.
    if len(body) > MAX_TEXT_LEN:
        return ParsedIntent(
            action="delete_entry",
            fields={},
            error=f"Search text is too long (max {MAX_TEXT_LEN} characters).",
        )
    return ParsedIntent(action="delete_entry", fields={"text": body})


def _parse_reset(raw: str) -> ParsedIntent | None:
    if not _RESET_FRAME.match(raw):
        return None
    lowered = raw.lower()
    if "lofi" in lowered or "stream" in lowered:
        scope = "lofi"
    elif "kiosk" in lowered:
        scope = "kiosk"
    else:
        scope = "all"
    return ParsedIntent(action="reset_frame", fields={"scope": scope})


def _parse_stream(raw: str) -> ParsedIntent | None:
    if _STREAM_STOP.match(raw):
        return ParsedIntent(action="stream_control", fields={"command": "stop"})
    if _STREAM_START.match(raw):
        return ParsedIntent(action="stream_control", fields={"command": "start"})
    return None


def _parse_person(raw: str) -> ParsedIntent | None:
    match = _PERSON_CMD.match(raw)
    if not match:
        return None
    rest = match.group(1).strip()
    color = None
    color_match = _COLOR.search(rest)
    if color_match:
        color = normalize_hex_color("#" + color_match.group(1))
        if color is None:
            return ParsedIntent(action="create_person", fields={}, error="Invalid color; use #RRGGBB.")
        rest = (rest[: color_match.start()] + rest[color_match.end() :]).strip()
        rest = re.sub(r"\s+", " ", rest)
    name = rest.strip(" ,:-")
    if not name:
        return ParsedIntent(action="create_person", fields={}, error="Name is required.")
    if len(name) > MAX_NAME_LEN:
        return ParsedIntent(
            action="create_person",
            fields={},
            error=f"Name is too long (max {MAX_NAME_LEN} characters).",
        )
    fields: dict[str, Any] = {"name": name}
    if color:
        fields["color"] = color
    return ParsedIntent(action="create_person", fields=fields)


def _parse_calendar(raw: str, *, today: date) -> ParsedIntent | None:
    entry_type = "chore"
    body = raw

    type_match = _TYPE_PREFIX.match(raw)
    if type_match:
        entry_type = type_match.group(1).lower()
        body = type_match.group(2).strip()
    else:
        # Allow "tomorrow: ..." / "today ..." without an explicit type → chore
        lowered = raw.lower()
        if not (
            lowered.startswith("today")
            or lowered.startswith("tomorrow")
            or any(lowered.startswith(day) for day in _WEEKDAYS)
            or _ISO_DATE.match(raw.split()[0] if raw.split() else "")
        ):
            return None

    person_name = None
    for_match = _FOR_PERSON.search(body)
    if for_match:
        person_name = for_match.group(1).strip()
        body = body[: for_match.start()].strip()

    entry_date, remainder = _consume_date(body, today=today)
    if entry_date is None:
        return ParsedIntent(
            action="create_entry",
            fields={},
            error="Could not find a date (try today, tomorrow, Friday, or YYYY-MM-DD).",
        )

    text = remainder.strip(" :,-")
    if not text:
        return ParsedIntent(action="create_entry", fields={}, error="Entry text is required.")
    if len(text) > MAX_TEXT_LEN:
        return ParsedIntent(
            action="create_entry",
            fields={},
            error=f"Entry text is too long (max {MAX_TEXT_LEN} characters).",
        )

    fields: dict[str, Any] = {
        "entry_type": entry_type,
        "entry_date": entry_date.isoformat(),
        "text": text,
    }
    if person_name:
        fields["person"] = person_name
    return ParsedIntent(action="create_entry", fields=fields)


def _consume_date(body: str, *, today: date) -> tuple[date | None, str]:
    """Pull a leading date token/phrase from body; return (date, remainder)."""
    parts = body.split(None, 1)
    if not parts:
        return None, body
    token = parts[0].rstrip(":,")
    remainder = parts[1] if len(parts) > 1 else ""

    lowered = token.lower()
    if lowered == "today":
        return today, remainder
    if lowered == "tomorrow":
        return today + timedelta(days=1), remainder

    iso = _ISO_DATE.match(token)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), remainder
        except ValueError:
            return None, body

    if lowered in _WEEKDAYS:
        return _next_weekday(today, _WEEKDAYS[lowered]), remainder

    return None, body


def _next_weekday(today: date, weekday: int) -> date:
    """Next occurrence of weekday (0=Mon), including today if it matches."""
    delta = (weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def merge_structured(payload: dict[str, Any], *, today: date | None = None) -> ParsedIntent:
    """
    Build an intent from structured JSON fields, falling back to text parse.

    Explicit structured fields win over parsed guesses when both exist.
    """
    today = today or today_local()
    intent = (payload.get("intent") or "").strip().lower()
    text = (payload.get("text") or "").strip()
    name = (payload.get("name") or "").strip()
    entry_date = (payload.get("entry_date") or "").strip()
    entry_type = (payload.get("entry_type") or "").strip().lower()
    person = (payload.get("person") or "").strip()
    command = (payload.get("command") or "").strip().lower()
    scope = (payload.get("scope") or "").strip().lower()

    if intent in ("reset", "restart"):
        if scope not in ("all", "lofi", "kiosk") and text:
            parsed = parse_text(text, today=today)
            if parsed.action == "reset_frame":
                return parsed
        if scope not in ("all", "lofi", "kiosk"):
            scope = "all"
        return ParsedIntent(action="reset_frame", fields={"scope": scope})

    if intent in ("list", "list_entries", "list_calendar"):
        if entry_date:
            if not _ISO_DATE.match(entry_date):
                d, rem = _consume_date(entry_date, today=today)
                if d is None or rem.strip():
                    return ParsedIntent(
                        action="list_entries",
                        fields={},
                        error="entry_date must be YYYY-MM-DD or today/tomorrow/weekday.",
                    )
                entry_date = d.isoformat()
            return ParsedIntent(action="list_entries", fields={"entry_date": entry_date})
        if text:
            parsed = parse_text(text, today=today)
            if parsed.action == "list_entries":
                return parsed
            listed = _parse_list_entries(f"list events on {text}", today=today)
            if listed is not None:
                return listed
        return ParsedIntent(
            action="list_entries",
            fields={},
            error="Provide entry_date or a day name to list.",
        )

    if intent in ("delete", "delete_calendar", "delete_entry"):
        ids_raw = payload.get("entry_ids")
        if ids_raw is not None:
            try:
                entry_ids = [int(x) for x in ids_raw]
            except (TypeError, ValueError):
                return ParsedIntent(
                    action="delete_entry",
                    fields={},
                    error="entry_ids must be a list of integers.",
                )
            if not entry_ids:
                return ParsedIntent(
                    action="delete_entry",
                    fields={},
                    error="entry_ids must not be empty.",
                )
            return ParsedIntent(action="delete_entry", fields={"entry_ids": entry_ids})
        entry_id_raw = payload.get("entry_id")
        if entry_id_raw is not None and str(entry_id_raw).strip() != "":
            try:
                entry_id = int(entry_id_raw)
            except (TypeError, ValueError):
                return ParsedIntent(
                    action="delete_entry",
                    fields={},
                    error="entry_id must be an integer.",
                )
            return ParsedIntent(action="delete_entry", fields={"entry_id": entry_id})
        if text:
            parsed = parse_text(text, today=today)
            if parsed.action in ("delete_entry", "list_entries"):
                return parsed
            # Allow structured delete fields with optional text phrase
            parsed = parse_text(f"delete {text}", today=today)
            if parsed.action == "delete_entry":
                return parsed
        fields: dict[str, Any] = {}
        if entry_date:
            fields["entry_date"] = entry_date
        if entry_type in ENTRY_TYPES:
            fields["entry_type"] = entry_type
        if person:
            fields["person"] = person
        entry_text = (payload.get("text") or "").strip()
        # Avoid treating the whole free-text command as the match string when intent is set
        if entry_text and not entry_text.lower().startswith(("delete ", "remove ", "cancel ")):
            fields["text"] = entry_text
        if not fields:
            return ParsedIntent(
                action="delete_entry",
                fields={},
                error="Provide entry_id, or date/text to match an entry to delete.",
            )
        return ParsedIntent(action="delete_entry", fields=fields)

    # Stream control: explicit intent, or bare command stop/start with no calendar/person fields.
    streamish = intent in ("stream", "lofi", "music")
    bare_stream_cmd = (
        command in ("stop", "start")
        and not name
        and not entry_date
        and entry_type not in ENTRY_TYPES
        and intent in ("", "stream", "lofi", "music")
    )
    if streamish or bare_stream_cmd:
        cmd = command
        if cmd not in ("stop", "start"):
            if text:
                parsed = parse_text(text, today=today)
                if parsed.action == "stream_control":
                    return parsed
            return ParsedIntent(
                action="stream_control",
                fields={},
                error="Stream command must be 'stop' or 'start' (or say 'stop stream').",
            )
        return ParsedIntent(action="stream_control", fields={"command": cmd})

    wants_person = intent == "person" or (bool(name) and intent != "calendar" and not entry_date)
    wants_calendar = intent == "calendar" or bool(entry_date) or entry_type in ENTRY_TYPES

    if wants_person and not wants_calendar:
        parsed_name = name
        parsed_color = payload.get("color")
        if not parsed_name and text:
            parsed = parse_text(text, today=today)
            if parsed.error:
                return parsed
            if parsed.action != "create_person":
                return ParsedIntent(action="create_person", fields={}, error="Expected a person.")
            parsed_name = parsed.fields.get("name", "")
            if parsed_color is None and "color" in parsed.fields:
                parsed_color = parsed.fields["color"]
        if not parsed_name:
            return ParsedIntent(action="create_person", fields={}, error="Name is required.")
        if len(parsed_name) > MAX_NAME_LEN:
            return ParsedIntent(
                action="create_person",
                fields={},
                error=f"Name is too long (max {MAX_NAME_LEN} characters).",
            )
        fields: dict[str, Any] = {"name": parsed_name}
        if parsed_color:
            color = normalize_hex_color(str(parsed_color))
            if color is None:
                return ParsedIntent(
                    action="create_person",
                    fields={},
                    error="Invalid color; use #RRGGBB.",
                )
            fields["color"] = color
        return ParsedIntent(action="create_person", fields=fields)

    if wants_calendar:
        entry_text = text
        if not entry_date and text:
            parsed = parse_text(text, today=today)
            if parsed.error:
                return parsed
            if parsed.action != "create_entry":
                return ParsedIntent(
                    action="create_entry",
                    fields={},
                    error="Expected a calendar entry.",
                )
            entry_date = parsed.fields.get("entry_date", "")
            if entry_type not in ENTRY_TYPES:
                entry_type = parsed.fields.get("entry_type", "chore")
            entry_text = parsed.fields.get("text", "")
            person = person or parsed.fields.get("person", "")

        if entry_type not in ENTRY_TYPES:
            entry_type = "chore"
        if not entry_date or not entry_text:
            return ParsedIntent(
                action="create_entry",
                fields={},
                error="Date and text are required.",
            )
        if not _ISO_DATE.match(entry_date):
            d, _ = _consume_date(entry_date, today=today)
            if d is None:
                return ParsedIntent(
                    action="create_entry",
                    fields={},
                    error="entry_date must be YYYY-MM-DD or today/tomorrow/weekday.",
                )
            entry_date = d.isoformat()
        if len(entry_text) > MAX_TEXT_LEN:
            return ParsedIntent(
                action="create_entry",
                fields={},
                error=f"Entry text is too long (max {MAX_TEXT_LEN} characters).",
            )
        fields = {
            "entry_type": entry_type,
            "entry_date": entry_date,
            "text": entry_text,
        }
        if person:
            fields["person"] = person
        return ParsedIntent(action="create_entry", fields=fields)

    if text:
        return parse_text(text, today=today)

    return ParsedIntent(
        action="",
        fields={},
        error="Provide structured fields or a 'text' message.",
    )
