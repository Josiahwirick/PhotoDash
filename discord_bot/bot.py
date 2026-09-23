#!/usr/bin/env python3
"""Thin Discord gateway bot that forwards messages to PhotoDash /api/webhook."""

from __future__ import annotations

import logging
import os
import sys

import discord
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("photodash-discord")

HELP_TEXT = """PhotoDash bot — send a message like:

• `add person Estelle #7cb89a`
• `chore tomorrow: take out trash for Estelle`
• `appointment Friday dentist`
• `reminder today pack lunch`
• `stop stream` / `start stream` (lofi)
• `reset frame` — soft-restart app + kiosk + lofi (no reboot)

Or say `help` for this message.
"""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def post_webhook(text: str) -> tuple[bool, str]:
    url = _env("PHOTODASH_WEBHOOK_URL", "http://127.0.0.1:8080/api/webhook")
    token = _env("PHOTODASH_WEBHOOK_TOKEN")
    if not token:
        return False, "PHOTODASH_WEBHOOK_TOKEN is not configured."
    try:
        res = requests.post(
            url,
            json={"text": text},
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

    action = data.get("action")
    result = data.get("result") or {}
    if action == "create_person":
        return True, f"Added person **{result.get('name')}**."
    if action == "create_entry":
        who = result.get("person_name")
        suffix = f" for {who}" if who else ""
        return True, (
            f"Added {result.get('entry_type')} on {result.get('entry_date')}: "
            f"{result.get('text')}{suffix}."
        )
    if action == "stream_control":
        if result.get("state") == "stopped":
            return True, "Lofi stream paused."
        if result.get("state") == "playing":
            return True, "Lofi stream playing."
        return True, f"Stream {result.get('command', 'updated')}."
    if action == "reset_frame":
        return True, f"Reset started ({result.get('scope', 'all')}). Give it ~15 seconds."
    return True, "Done."


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

        ok, reply = post_webhook(content)
        await message.channel.send(reply if ok else f"Sorry — {reply}")

    client.run(bot_token, log_handler=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
