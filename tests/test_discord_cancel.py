"""Tests for Discord cancel-event numbered selection helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "discord_bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from cancel_flow import (  # noqa: E402
    build_pending,
    format_list_reply,
    parse_selection,
    resolve_selection,
)


def test_parse_selection_numbers():
    assert parse_selection("1") == [1]
    assert parse_selection("1 3") == [1, 3]
    assert parse_selection("1, 2, 3") == [1, 2, 3]
    assert parse_selection("1 and 3") == [1, 3]


def test_parse_selection_abort():
    assert parse_selection("nevermind") == []
    assert parse_selection("cancel") == []
    assert parse_selection("nvm") == []


def test_parse_selection_unrelated():
    assert parse_selection("chore tomorrow: trash") is None
    assert parse_selection("cancel event on Friday") is None


def test_build_and_resolve():
    pending = build_pending(
        "2026-09-27",
        [
            {"id": 10, "entry_type": "chore", "text": "a", "person_name": None},
            {"id": 11, "entry_type": "appointment", "text": "b", "person_name": "Estelle"},
        ],
    )
    reply = format_list_reply(pending)
    assert "1." in reply and "2." in reply
    assert "chore: a" in reply
    ids, invalid = resolve_selection(pending, [2, 9, 1])
    assert ids == [11, 10]
    assert invalid == [9]
