#!/usr/bin/env bash
# Install / update the PhotoDash Discord bot companion.
#
#   sudo ./discord_bot/install.sh
#
# Requires DISCORD_BOT_TOKEN (and usually PHOTODASH_WEBHOOK_TOKEN) in the
# environment or already present in /etc/photodash-discord.env.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${PHOTODASH_APP_ROOT:-/opt/photodash}"
BOT_ROOT="${APP_ROOT}/discord_bot"
ENV_FILE="/etc/photodash-discord.env"

log() { printf '\n==> %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo ./discord_bot/install.sh"
id photodash >/dev/null 2>&1 || die "photodash user missing; run the main install.sh first"

log "Syncing Discord bot to $BOT_ROOT"
mkdir -p "$BOT_ROOT"
rsync -a --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  "$REPO_ROOT/discord_bot/" "$BOT_ROOT/"

if [[ ! -d "$BOT_ROOT/.venv" ]]; then
  python3 -m venv "$BOT_ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$BOT_ROOT/.venv/bin/activate"
pip install --upgrade pip wheel
pip install -r "$BOT_ROOT/requirements.txt"
deactivate
chown -R photodash:photodash "$BOT_ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 600 "$REPO_ROOT/deploy/photodash-discord.env.example" "$ENV_FILE"
fi

# Merge tokens from environment when provided
if [[ -n "${DISCORD_BOT_TOKEN:-}" ]]; then
  if grep -q '^DISCORD_BOT_TOKEN=' "$ENV_FILE"; then
    sed -i "s|^DISCORD_BOT_TOKEN=.*|DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}|" "$ENV_FILE"
  else
    echo "DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}" >> "$ENV_FILE"
  fi
fi
if [[ -n "${PHOTODASH_WEBHOOK_TOKEN:-}" ]]; then
  if grep -q '^PHOTODASH_WEBHOOK_TOKEN=' "$ENV_FILE"; then
    sed -i "s|^PHOTODASH_WEBHOOK_TOKEN=.*|PHOTODASH_WEBHOOK_TOKEN=${PHOTODASH_WEBHOOK_TOKEN}|" "$ENV_FILE"
  else
    echo "PHOTODASH_WEBHOOK_TOKEN=${PHOTODASH_WEBHOOK_TOKEN}" >> "$ENV_FILE"
  fi
fi
if [[ -n "${DISCORD_CHANNEL_ID:-}" ]]; then
  if grep -q '^DISCORD_CHANNEL_ID=' "$ENV_FILE"; then
    sed -i "s|^DISCORD_CHANNEL_ID=.*|DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}|" "$ENV_FILE"
  else
    echo "DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}" >> "$ENV_FILE"
  fi
fi
chmod 600 "$ENV_FILE"
chown root:photodash "$ENV_FILE" 2>/dev/null || true

# Pull webhook token from app settings DB if still empty
if ! grep -q '^PHOTODASH_WEBHOOK_TOKEN=.\+' "$ENV_FILE"; then
  if [[ -x "$APP_ROOT/.venv/bin/python" && -f /var/lib/photodash/photodash.db ]]; then
    token="$("$APP_ROOT/.venv/bin/python" - <<'PY'
import sqlite3
conn = sqlite3.connect("/var/lib/photodash/photodash.db")
row = conn.execute("SELECT value FROM settings WHERE key='webhook_token'").fetchone()
print(row[0] if row and row[0] else "")
PY
)"
    if [[ -n "$token" ]]; then
      sed -i "s|^PHOTODASH_WEBHOOK_TOKEN=.*|PHOTODASH_WEBHOOK_TOKEN=${token}|" "$ENV_FILE"
    fi
  fi
fi

install -m 644 "$REPO_ROOT/deploy/photodash-discord.service" /etc/systemd/system/photodash-discord.service
systemctl daemon-reload

if grep -q '^DISCORD_BOT_TOKEN=.\+' "$ENV_FILE"; then
  log "Enabling photodash-discord.service"
  systemctl enable photodash-discord.service
  systemctl restart photodash-discord.service
  systemctl --no-pager --full status photodash-discord.service || true
else
  echo "DISCORD_BOT_TOKEN not set in $ENV_FILE — service installed but not enabled."
  echo "Add the token, then: systemctl enable --now photodash-discord"
fi

echo
echo "Discord bot install complete."
echo "Env file: $ENV_FILE"
