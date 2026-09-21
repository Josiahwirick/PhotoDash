#!/usr/bin/env bash
# Install / update the optional PhotoDash CLIAMP lofi companion.
#
#   sudo ./scripts/install_lofi.sh
#
# Installs the cliamp binary (linux arm64/amd64), systemd unit, shared socket
# dir, and marks the feature installed in SQLite settings.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${PHOTODASH_APP_ROOT:-/opt/photodash}"
DATA_DIR="${PHOTODASH_DATA_DIR:-/var/lib/photodash}"
DB_PATH="${DATA_DIR}/photodash.db"
CLIAMP_BIN="/usr/local/bin/cliamp"
CONFIG_DIR="${DATA_DIR}/cliamp"

log() { printf '\n==> %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo ./scripts/install_lofi.sh"
id photodash >/dev/null 2>&1 || die "photodash user missing; run the main install.sh first"

detect_kiosk_user() {
  if id pi >/dev/null 2>&1; then
    echo pi
  elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "$SUDO_USER"
  else
    getent passwd | awk -F: '$3>=1000 && $1!="nobody" {print $1; exit}'
  fi
}

arch="$(uname -m)"
case "$arch" in
  aarch64|arm64) asset="cliamp-linux-arm64" ;;
  x86_64|amd64) asset="cliamp-linux-amd64" ;;
  *) die "Unsupported architecture for cliamp: $arch (need arm64 or amd64)" ;;
esac

log "Installing cliamp ($asset)"
curl -fsSL -o /tmp/cliamp-download \
  "https://github.com/bjarneo/cliamp/releases/latest/download/${asset}"
install -m 755 /tmp/cliamp-download "$CLIAMP_BIN"
"$CLIAMP_BIN" --version || true

kiosk_user="$(detect_kiosk_user)"
[[ -n "$kiosk_user" ]] || die "Could not determine kiosk user"
kiosk_home="$(getent passwd "$kiosk_user" | cut -d: -f6)"
kiosk_uid="$(id -u "$kiosk_user")"

log "Preparing shared config dir $CONFIG_DIR"
mkdir -p "$CONFIG_DIR"
chown "${kiosk_user}:photodash" "$CONFIG_DIR"
chmod 2770 "$CONFIG_DIR"

log "Installing photodash-cliamp.service"
sed \
  -e "s|KIOSK_USER|${kiosk_user}|g" \
  -e "s|KIOSK_HOME|${kiosk_home}|g" \
  -e "s|KIOSK_UID|${kiosk_uid}|g" \
  "$REPO_ROOT/deploy/photodash-cliamp.service" \
  > /etc/systemd/system/photodash-cliamp.service

mkdir -p /etc/systemd/system/photodash.service.d
cat > /etc/systemd/system/photodash.service.d/cliamp.conf <<EOF
[Service]
Environment=CLIAMP_CONFIG_DIR=${CONFIG_DIR}
EOF

# Mark feature installed + enabled in settings DB
if [[ -f "$DB_PATH" ]]; then
  log "Enabling lofi feature in settings"
  if [[ -x "$APP_ROOT/.venv/bin/python" ]]; then
    "$APP_ROOT/.venv/bin/python" - <<PY
import sqlite3
conn = sqlite3.connect("$DB_PATH")
for key, value in (("lofi_installed", "1"), ("lofi_enabled", "1")):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
conn.commit()
conn.close()
print("lofi_installed=1 lofi_enabled=1")
PY
  fi
fi

systemctl daemon-reload
systemctl enable photodash-cliamp.service
systemctl restart photodash-cliamp.service
systemctl restart photodash.service || true
systemctl --no-pager --full status photodash-cliamp.service || true

echo
echo "Lofi companion installed."
echo "Toggle the strip under Admin → Settings (only shown when installed)."
echo "Logs: journalctl -u photodash-cliamp -f"
