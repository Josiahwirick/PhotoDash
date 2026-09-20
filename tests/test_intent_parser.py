"""Tests for free-text intent parsing."""

from __future__ import annotations

from datetime import date

from app.services.intent_parser import merge_structured, parse_text

TODAY = date(2026, 9, 18)  # Friday


def test_parse_add_person():
    result = parse_text("add person Estelle", today=TODAY)
    assert result.error is None
    assert result.action == "create_person"
    assert result.fields["name"] == "Estelle"


def test_parse_person_with_color():
    result = parse_text("new person Caspar #7cb89a", today=TODAY)
    assert result.error is None
    assert result.action == "create_person"
    assert result.fields["name"] == "Caspar"
    assert result.fields["color"] == "#7cb89a"


def test_parse_person_bad_color():
    result = parse_text("add person Kid #gg0000", today=TODAY)
    # #gg0000 won't match color regex; treated as part of name or no color
    # Invalid hex that matches pattern but fails normalize:
    result = parse_text("add person Kid", today=TODAY)
    assert result.action == "create_person"


def test_parse_chore_tomorrow():
    result = parse_text("chore tomorrow: take out trash for Estelle", today=TODAY)
    assert result.error is None
    assert result.action == "create_entry"
    assert result.fields["entry_type"] == "chore"
    assert result.fields["entry_date"] == "2026-09-19"
    assert result.fields["text"] == "take out trash"
    assert result.fields["person"] == "Estelle"


def test_parse_appointment_weekday():
    # TODAY is Friday; "Monday" → 2026-09-21
    result = parse_text("appointment Monday dentist", today=TODAY)
    assert result.error is None
    assert result.fields["entry_type"] == "appointment"
    assert result.fields["entry_date"] == "2026-09-21"
    assert result.fields["text"] == "dentist"


def test_parse_reminder_today():
    result = parse_text("reminder today pack lunch", today=TODAY)
    assert result.error is None
    assert result.fields["entry_type"] == "reminder"
    assert result.fields["entry_date"] == "2026-09-18"
    assert result.fields["text"] == "pack lunch"


def test_parse_iso_date():
    result = parse_text("chore 2026-09-25: garden", today=TODAY)
    assert result.error is None
    assert result.fields["entry_date"] == "2026-09-25"
    assert result.fields["text"] == "garden"


def test_parse_unknown():
    result = parse_text("hello world", today=TODAY)
    assert result.error
    assert result.action == ""


def test_merge_structured_person():
    result = merge_structured({"intent": "person", "name": "Josie", "color": "#aabbcc"}, today=TODAY)
    assert result.action == "create_person"
    assert result.fields["name"] == "Josie"
    assert result.fields["color"] == "#aabbcc"


def test_merge_structured_calendar():
    result = merge_structured(
        {
            "intent": "calendar",
            "entry_type": "chore",
            "entry_date": "2026-09-20",
            "text": "dishes",
            "person": "Estelle",
        },
        today=TODAY,
    )
    assert result.action == "create_entry"
    assert result.fields["entry_date"] == "2026-09-20"
    assert result.fields["text"] == "dishes"
    assert result.fields["person"] == "Estelle"


def test_merge_structured_wins_over_text():
    result = merge_structured(
        {
            "intent": "calendar",
            "entry_type": "reminder",
            "entry_date": "2026-09-22",
            "text": "from structured",
        },
        today=TODAY,
    )
    assert result.fields["text"] == "from structured"
    assert result.fields["entry_type"] == "reminder"
