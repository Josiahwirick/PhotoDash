#!/usr/bin/env python3
"""Thin Discord gateway bot that forwards messages to PhotoDash /api/webhook."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import discord
import requests

# Allow `from cancel_flow import ...` when run as a script from systemd.
_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from cancel_flow import (  # noqa: E402
    PendingCancel,
    build_pending,
    format_list_reply,
    parse_selection,
    resolve_selection,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("photodash-discord")

HELP_TEXT = """PhotoDash bot — send a message like:

• `add person Estelle #7cb89a`
• `chore tomorrow: take out trash for Estelle`
• `appointment Friday dentist`
• `cancel event on Friday` — pick from a numbered list
• `cancel event on 2026-09-27`
• `delete chore tomorrow: take out trash`
• `stop stream` / `start stream` (lofi)
• `reset frame` — soft-restart app + kiosk + lofi (no reboot)

Or say `help` for this message.
"""

# (channel_id, user_id) → pending cancel picker
_pending: dict[tuple[int, int], PendingCancel] = {}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def post_webhook(payload: dict) -> tuple[bool, dict | str]:
    """POST JSON to PhotoDash webhook. Returns (ok, data_or_error_string)."""
    url = _env("PHOTODASH_WEBHOOK_URL", "http://127.0.0.1:8080/api/webhook")
    token = _env("PHOTODASH_WEBHOOK_TOKEN")
    if not token:
        return False, "PHOTODASH_WEBHOOK_TOKEN is not configured."
    try:
        res = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach PhotoDash: {exc}"

    try:
        data = res.json()
    except ValueError:
        return False, f"PhotoDash returned HTTP {res.status_code}."

    if res.status_code == 401:
        return False, "Webhook token rejected (check PHOTODASH_WEBHOOK_TOKEN)."
    if not data.get("ok"):
        return False, data.get("error") or f"Request failed (HTTP {res.status_code})."
    return True, data


def format_success(data: dict) -> str:
    action = data.get("action")
    result = data.get("result") or {}
    if action == "create_person":
        return f"Added person **{result.get('name')}**."
    if action == "create_entry":
        who = result.get("person_name")
        suffix = f" for {who}" if who else ""
        return (
            f"Added {result.get('entry_type')} on {result.get('entry_date')}: "
            f"{result.get('text')}{suffix}."
        )
    if action == "list_entries":
        pending = build_pending(
            str(result.get("entry_date") or ""),
            list(result.get("entries") or []),
        )
        return format_list_reply(pending)
    if action == "delete_entry":
        entries = result.get("entries") or []
        if not entries:
            return (
                f"Deleted {result.get('deleted', 0)} "
                f"entr{'y' if result.get('deleted') == 1 else 'ies'}."
            )
        if len(entries) == 1:
            e = entries[0]
            who = e.get("person_name")
            suffix = f" for {who}" if who else ""
            return (
                f"Deleted {e.get('entry_type')} on {e.get('entry_date')}: "
                f"{e.get('text')}{suffix}."
            )
        lines = [f"Deleted {len(entries)} entries:"]
        for e in entries:
            who = e.get("person_name")
            suffix = f" for {who}" if who else ""
            lines.append(f"• {e.get('entry_type')}: {e.get('text')}{suffix}")
        return "\n".join(lines)
    if action == "stream_control":
        if result.get("state") == "stopped":
            return "Lofi stream paused."
        if result.get("state") == "playing":
            return "Lofi stream playing."
        return f"Stream {result.get('command', 'updated')}."
    if action == "reset_frame":
        return f"Reset started ({result.get('scope', 'all')}). Give it ~15 seconds."
    return "Done."


def handle_message(content: str, *, channel_id: int, user_id: int) -> str:
    """Process one user message; may use pending cancel state."""
    key = (channel_id, user_id)
    pending = _pending.get(key)

    if pending is not None:
        selection = parse_selection(content)
        if selection is not None:
            _pending.pop(key, None)
            if not selection:
                return "Cancelled — nothing removed."
            entry_ids, invalid = resolve_selection(pending, selection)
            if invalid and not entry_ids:
                return (
                    f"Those numbers aren't on the list ({', '.join(map(str, invalid))}). "
                    "Say `cancel event on …` to try again."
                )
            if not entry_ids:
                return "Nothing to delete."
            ok, data = post_webhook({"intent": "delete", "entry_ids": entry_ids})
            if not ok:
                return f"Sorry — {data}"
            reply = format_success(data)  # type: ignore[arg-type]
            if invalid:
                reply += f"\n(Ignored invalid numbers: {', '.join(map(str, invalid))})"
            return reply
        # Unrelated message while pending — drop picker and continue.
        _pending.pop(key, None)

    ok, data = post_webhook({"text": content})
    if not ok:
        return f"Sorry — {data}"

    assert isinstance(data, dict)
    if data.get("action") == "list_entries":
        result = data.get("result") or {}
        entries = list(result.get("entries") or [])
        entry_date = str(result.get("entry_date") or "")
        built = build_pending(entry_date, entries)
        if built.choices:
            _pending[key] = built
        return format_list_reply(built)

    return format_success(data)


def main() -> int:
    bot_token = _env("DISCORD_BOT_TOKEN")
    if not bot_token:
        logger.error("DISCORD_BOT_TOKEN is required")
        return 1

    channel_raw = _env("DISCORD_CHANNEL_ID")
    channel_id = int(channel_raw) if channel_raw.isdigit() else None

    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("Logged in as %s", client.user)

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_channel = channel_id is not None and message.channel.id == channel_id
        if not is_dm and not is_channel:
            return

        content = (message.content or "").strip()
        if not content:
            return
        if content.lower() in {"help", "?", "commands"}:
            await message.channel.send(HELP_TEXT)
            return

        reply = handle_message(
            content,
            channel_id=message.channel.id,
            user_id=message.author.id,
        )
        await message.channel.send(reply)

    client.run(bot_token, log_handler=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
