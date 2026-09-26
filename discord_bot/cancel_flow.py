"""Pure helpers for Discord cancel-event numbered selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

_ABORT = frozenset({"cancel", "nevermind", "never mind", "abort", "nvm", "stop"})


@dataclass
class PendingCancel:
    """In-memory cancel picker for one Discord user in one channel."""

    entry_date: str
    choices: dict[int, int] = field(default_factory=dict)  # list number → entry id
    labels: dict[int, str] = field(default_factory=dict)


def format_entry_line(entry: dict[str, Any]) -> str:
    who = entry.get("person_name")
    suffix = f" for {who}" if who else ""
    return f"{entry.get('entry_type')}: {entry.get('text')}{suffix}"


def format_day_label(entry_date: str) -> str:
    try:
        d = date.fromisoformat(entry_date)
    except ValueError:
        return entry_date
    return f"{d.strftime('%A')} ({entry_date})"


def build_pending(entry_date: str, entries: list[dict[str, Any]]) -> PendingCancel:
    pending = PendingCancel(entry_date=entry_date)
    for i, entry in enumerate(entries, start=1):
        pending.choices[i] = int(entry["id"])
        pending.labels[i] = format_entry_line(entry)
    return pending


def format_list_reply(pending: PendingCancel) -> str:
    day = format_day_label(pending.entry_date)
    if not pending.choices:
        return f"No events on {day}."
    lines = [f"Events on {day} — reply with number(s) to cancel (or `nevermind`):", ""]
    for num in sorted(pending.choices):
        lines.append(f"**{num}.** {pending.labels[num]}")
    return "\n".join(lines)


def parse_selection(text: str) -> list[int] | None:
    """
    Parse a reply as abort ([]), selection numbers, or unrelated (None).

    Returns:
      [] — user aborted
      [1, 3] — selected list numbers
      None — not a selection message
    """
    raw = (text or "").strip()
    if not raw:
        return None
    low = re.sub(r"\s+", " ", raw.lower())
    if low in _ABORT:
        return []
    normalized = re.sub(r"\band\b", " ", low)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not re.fullmatch(r"[\d\s,;&\-]+", normalized):
        return None
    nums = [int(x) for x in re.findall(r"\d+", normalized)]
    return nums if nums else None


def resolve_selection(
    pending: PendingCancel, numbers: list[int]
) -> tuple[list[int], list[int]]:
    """Map list numbers to entry ids; return (entry_ids, invalid_numbers)."""
    ids: list[int] = []
    invalid: list[int] = []
    seen: set[int] = set()
    for num in numbers:
        if num not in pending.choices:
            invalid.append(num)
            continue
        eid = pending.choices[num]
        if eid not in seen:
            seen.add(eid)
            ids.append(eid)
    return ids, invalid
