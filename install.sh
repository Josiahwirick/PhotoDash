#!/usr/bin/env bash
# PhotoDash one-command installer for Raspberry Pi OS Lite (Debian-like).
#
#   sudo ./install.sh
#   sudo ./install.sh --non-interactive
#   sudo ./install.sh --no-kiosk
#   sudo ./install.sh --with-discord
#   sudo ./install.sh --update
#
# Non-interactive env overrides:
#   PHOTODASH_PASSWORD, SECRET_KEY, PHOTODASH_STORAGE_PATH,
#   PHOTODASH_WEATHER_LAT, PHOTODASH_WEATHER_LON, PHOTODASH_TIMEZONE,
#   DISCORD_BOT_TOKEN, PHOTODASH_WEBHOOK_TOKEN, DISCORD_CHANNEL_ID

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="/opt/photodash"
ENV_FILE="/etc/photodash.env"
DATA_DIR="/var/lib/photodash"
DEFAULT_STORAGE="/mnt/usb/photodash/photos"
FALLBACK_STORAGE="${DATA_DIR}/photos"

NON_INTERACTIVE=0
NO_KIOSK=0
WITH_DISCORD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    --no-kiosk) NO_KIOSK=1; shift ;;
    --with-discord) WITH_DISCORD=1; shift ;;
    --update) shift ;; # same path; idempotent re-install
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo ./install.sh"

prompt() {
  local __var="$1" __message="$2" __default="${3:-}" __reply
  if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
    printf -v "$__var" '%s' "$__default"
    return
  fi
  if [[ -n "$__default" ]]; then
    read -r -p "$__message [$__default]: " __reply || true
    printf -v "$__var" '%s' "${__reply:-$__default}"
  else
    read -r -p "$__message: " __reply || true
    printf -v "$__var" '%s' "$__reply"
  fi
}

prompt_secret() {
  local __var="$1" __message="$2" __default="${3:-}" __reply
  if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
    printf -v "$__var" '%s' "$__default"
    return
  fi
  read -r -s -p "$__message: " __reply || true
  echo
  if [[ -z "$__reply" && -n "$__default" ]]; then
    printf -v "$__var" '%s' "$__default"
  else
    printf -v "$__var" '%s' "$__reply"
  fi
}

detect_kiosk_user() {
  if id pi >/dev/null 2>&1; then
    echo pi
  elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "$SUDO_USER"
  else
    getent passwd | awk -F: '$3>=1000 && $1!="nobody" {print $1; exit}'
  fi
}

install_packages() {
  log "Installing system packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  local pkgs=(
    python3 python3-venv python3-dev python3-pip
    libjpeg-dev zlib1g-dev libfreetype6-dev
    curl rsync avahi-daemon
  )
  if [[ "$NO_KIOSK" -eq 0 ]]; then
    pkgs+=(
      xserver-xorg xinit x11-xserver-utils
      matchbox-window-manager unclutter
    )
    if apt-cache show chromium-browser >/dev/null 2>&1; then
      pkgs+=(chromium-browser)
    elif apt-cache show chromium >/dev/null 2>&1; then
      pkgs+=(chromium)
    else
      echo "WARNING: No chromium package found; install Chromium before enabling kiosk."
    fi
  fi
  apt-get install -y "${pkgs[@]}"
}

ensure_users() {
  log "Ensuring system users"
  if ! id photodash >/dev/null 2>&1; then
    useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin photodash
  fi
  local kiosk_user
  kiosk_user="$(detect_kiosk_user)"
  [[ -n "$kiosk_user" ]] || die "Could not determine kiosk user"
  if ! id "$kiosk_user" >/dev/null 2>&1; then
    die "Kiosk user '$kiosk_user' does not exist"
  fi
  usermod -aG video,input,render "$kiosk_user" 2>/dev/null || usermod -aG video,input "$kiosk_user" || true
}

sync_app() {
  log "Installing application to $APP_ROOT"
  mkdir -p "$APP_ROOT" "$DATA_DIR" "$FALLBACK_STORAGE"
  rsync -a --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'data/' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env' \
    "$REPO_ROOT/" "$APP_ROOT/"

  if [[ ! -d "$APP_ROOT/.venv" ]]; then
    python3 -m venv "$APP_ROOT/.venv"
  fi
  # shellcheck disable=SC1091
  source "$APP_ROOT/.venv/bin/activate"
  pip install --upgrade pip wheel
  pip install -r "$APP_ROOT/requirements.txt"
  deactivate

  chown -R photodash:photodash "$APP_ROOT" "$DATA_DIR"
}

configure_env() {
  log "Configuring $ENV_FILE"
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a || true
  fi

  SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"
  local admin_password storage_path weather_lat weather_lon weather_tz
  if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
    admin_password="${PHOTODASH_PASSWORD:-photodash}"
    storage_path="${PHOTODASH_STORAGE_PATH:-$DEFAULT_STORAGE}"
    weather_lat="${PHOTODASH_WEATHER_LAT:-}"
    weather_lon="${PHOTODASH_WEATHER_LON:-}"
    weather_tz="${PHOTODASH_TIMEZONE:-America/New_York}"
  else
    prompt_secret admin_password "Admin password" "${PHOTODASH_PASSWORD:-photodash}"
    [[ -n "$admin_password" ]] || admin_password="photodash"
    prompt storage_path "Photo storage path" "${PHOTODASH_STORAGE_PATH:-$DEFAULT_STORAGE}"
    prompt weather_lat "Weather latitude (blank to configure later)" "${PHOTODASH_WEATHER_LAT:-}"
    prompt weather_lon "Weather longitude (blank to configure later)" "${PHOTODASH_WEATHER_LON:-}"
    prompt weather_tz "IANA timezone" "${PHOTODASH_TIMEZONE:-America/New_York}"
  fi

  mkdir -p "$(dirname "$ENV_FILE")" "$DATA_DIR" "$FALLBACK_STORAGE"
  mkdir -p "$storage_path" 2>/dev/null || true

  python3 "$REPO_ROOT/scripts/write_env_file.py" "$ENV_FILE" \
    "SECRET_KEY=${SECRET_KEY}" \
    "PHOTODASH_DB_PATH=${DATA_DIR}/photodash.db" \
    "PHOTODASH_STORAGE_PATH=${storage_path}" \
    "PHOTODASH_FALLBACK_STORAGE_PATH=${FALLBACK_STORAGE}" \
    "PHOTODASH_HOST=0.0.0.0" \
    "PHOTODASH_PORT=8080"
  chmod 600 "$ENV_FILE"
  chown root:photodash "$ENV_FILE" 2>/dev/null || true
  chown -R photodash:photodash "$DATA_DIR" "$FALLBACK_STORAGE"
  chown -R photodash:photodash "$storage_path" 2>/dev/null || true

  # Bootstrap password is passed to migrate only (not persisted in the env file).
  export PHOTODASH_PASSWORD="$admin_password"
  export PHOTODASH_DB_PATH="$DATA_DIR/photodash.db"
  export PHOTODASH_STORAGE_PATH="$storage_path"
  export WEATHER_LAT="$weather_lat"
  export WEATHER_LON="$weather_lon"
  export WEATHER_TZ="$weather_tz"
}

migrate_db() {
  log "Migrating database"
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  sudo -u photodash env \
    PHOTODASH_DB_PATH="${PHOTODASH_DB_PATH:-$DATA_DIR/photodash.db}" \
    PHOTODASH_PASSWORD="${PHOTODASH_PASSWORD:-}" \
    PHOTODASH_STORAGE_PATH="${PHOTODASH_STORAGE_PATH:-}" \
    "$APP_ROOT/.venv/bin/python" "$APP_ROOT/scripts/migrate.py" \
      --db "${PHOTODASH_DB_PATH:-$DATA_DIR/photodash.db}" \
      --password "${PHOTODASH_PASSWORD:-}"
}

persist_weather_settings() {
  log "Seeding weather settings"
  sudo -u photodash env \
    PHOTODASH_DB_PATH="$DATA_DIR/photodash.db" \
    WEATHER_LAT="${WEATHER_LAT:-}" \
    WEATHER_LON="${WEATHER_LON:-}" \
    WEATHER_TZ="${WEATHER_TZ:-America/New_York}" \
    "$APP_ROOT/.venv/bin/python" - <<'PY'
import os
import sqlite3
from pathlib import Path

db = Path(os.environ["PHOTODASH_DB_PATH"])
conn = sqlite3.connect(db)
vals = {
    "weather_latitude": os.environ.get("WEATHER_LAT", ""),
    "weather_longitude": os.environ.get("WEATHER_LON", ""),
    "weather_timezone": os.environ.get("WEATHER_TZ", "America/New_York"),
}
for key, value in vals.items():
    if not value:
        continue
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
conn.commit()
conn.close()
print("Weather settings updated")
PY
}

install_units() {
  log "Installing systemd units"
  install -d /etc/photodash
  install -m 755 "$REPO_ROOT/deploy/xinitrc" /etc/photodash/xinitrc
  install -m 644 "$REPO_ROOT/deploy/photodash.service" /etc/systemd/system/photodash.service

  if [[ "$NO_KIOSK" -eq 0 ]]; then
    local kiosk_user kiosk_home
    kiosk_user="$(detect_kiosk_user)"
    kiosk_home="$(getent passwd "$kiosk_user" | cut -d: -f6)"
    sed -e "s|KIOSK_USER|$kiosk_user|g" -e "s|KIOSK_HOME|$kiosk_home|g" \
      "$REPO_ROOT/deploy/photodash-kiosk.service" > /etc/systemd/system/photodash-kiosk.service
  fi

  systemctl daemon-reload
  systemctl enable photodash.service
  systemctl restart photodash.service

  if [[ "$NO_KIOSK" -eq 0 ]]; then
    systemctl enable photodash-kiosk.service
    systemctl set-default graphical.target || true
    systemctl restart photodash-kiosk.service || true
  fi
}

wait_health() {
  log "Waiting for health endpoint"
  local i
  for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8080/health >/dev/null; then
      echo "PhotoDash is up."
      return 0
    fi
    sleep 1
  done
  echo "WARNING: health check did not succeed; check: journalctl -u photodash -e"
}

print_summary() {
  local ip host
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  host="$(hostname 2>/dev/null || echo photodash)"
  echo
  echo "============================================"
  echo " PhotoDash installed"
  echo " Frame:  http://${ip:-<pi-ip>}:8080/"
  echo " Admin:  http://${ip:-<pi-ip>}:8080/admin"
  echo " mDNS:   http://${host}.local:8080/admin"
  echo " Logs:   journalctl -u photodash -f"
  echo "============================================"
}

install_packages
ensure_users
sync_app
configure_env
migrate_db
persist_weather_settings
install_units
wait_health

if [[ "$WITH_DISCORD" -eq 1 ]] || [[ -n "${DISCORD_BOT_TOKEN:-}" ]]; then
  log "Installing Discord bot"
  bash "$REPO_ROOT/discord_bot/install.sh"
fi

print_summary
