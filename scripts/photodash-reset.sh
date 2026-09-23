#!/usr/bin/env bash
# Soft-reset PhotoDash + optional companions without rebooting the Pi.
#
#   sudo photodash-reset
#   sudo photodash-reset --lofi-only
#   sudo photodash-reset --kiosk-only
#
# Safe to run while the frame is frozen or lofi/Discord controls are wedged.

set -euo pipefail

LOFI_ONLY=0
KIOSK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --lofi-only) LOFI_ONLY=1 ;;
    --kiosk-only) KIOSK_ONLY=1 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root: sudo photodash-reset" >&2; exit 1; }

CONFIG_DIR="${CLIAMP_CONFIG_DIR:-/var/lib/photodash/cliamp}"
SOCK="${CONFIG_DIR}/cliamp.sock"
PIDFILE="${CONFIG_DIR}/cliamp.sock.pid"

log() { printf '==> %s\n' "$*"; }

clear_stale_cliamp() {
  log "Clearing stale CLIAMP IPC state"
  # Kill only real cliamp processes (never trust the pidfile alone — it has
  # been observed to point at gunicorn after a crash).
  pkill -x cliamp 2>/dev/null || true
  sleep 0.5
  pkill -9 -x cliamp 2>/dev/null || true
  rm -f "$SOCK" "$PIDFILE"
  mkdir -p "$CONFIG_DIR"
  # Kiosk user owns the dir; photodash group can share the socket later.
  if id pi >/dev/null 2>&1; then
    chown pi:photodash "$CONFIG_DIR" 2>/dev/null || true
  fi
  chmod 2770 "$CONFIG_DIR" 2>/dev/null || true
}

fix_cliamp_socket() {
  local i
  for i in $(seq 1 20); do
    if [[ -S "$SOCK" ]]; then
      chgrp photodash "$SOCK" 2>/dev/null || true
      chmod 660 "$SOCK" 2>/dev/null || true
      return 0
    fi
    sleep 0.4
  done
  return 0
}

if [[ "$KIOSK_ONLY" -eq 1 ]]; then
  log "Restarting kiosk only"
  systemctl restart photodash-kiosk.service
  log "Done."
  exit 0
fi

if [[ "$LOFI_ONLY" -eq 1 ]]; then
  if systemctl cat photodash-cliamp.service >/dev/null 2>&1; then
    systemctl stop photodash-cliamp.service 2>/dev/null || true
    clear_stale_cliamp
    systemctl reset-failed photodash-cliamp.service 2>/dev/null || true
    systemctl start photodash-cliamp.service
    fix_cliamp_socket
    systemctl start photodash-cliamp-socketperm.service 2>/dev/null || true
  else
    log "photodash-cliamp not installed; nothing to do"
  fi
  log "Done."
  exit 0
fi

log "Stopping companions"
systemctl stop photodash-cliamp.service 2>/dev/null || true
systemctl stop photodash-kiosk.service 2>/dev/null || true

clear_stale_cliamp

log "Restarting PhotoDash app"
systemctl reset-failed photodash.service 2>/dev/null || true
systemctl restart photodash.service
sleep 2

if systemctl cat photodash-cliamp.service >/dev/null 2>&1 \
  && systemctl is-enabled photodash-cliamp.service >/dev/null 2>&1; then
  log "Restarting CLIAMP lofi"
  systemctl reset-failed photodash-cliamp.service 2>/dev/null || true
  systemctl start photodash-cliamp.service
  fix_cliamp_socket
  systemctl start photodash-cliamp-socketperm.service 2>/dev/null || true
fi

if systemctl cat photodash-kiosk.service >/dev/null 2>&1; then
  log "Restarting Chromium kiosk"
  # Give X time to die after stop; leftover chromium locks the display.
  sleep 2
  pkill -u "$(id -un pi 2>/dev/null || echo pi)" -f '[c]hromium' 2>/dev/null || true
  pkill -u "$(id -un pi 2>/dev/null || echo pi)" -f '[X]org|[X]wayland|X :0' 2>/dev/null || true
  sleep 1
  systemctl reset-failed photodash-kiosk.service 2>/dev/null || true
  systemctl start photodash-kiosk.service
  sleep 2
  systemctl is-active photodash-kiosk.service || log "WARNING: kiosk failed to start — run: systemctl status photodash-kiosk"
fi

if systemctl cat photodash-discord.service >/dev/null 2>&1 \
  && systemctl is-enabled photodash-discord.service >/dev/null 2>&1; then
  log "Restarting Discord bot"
  systemctl reset-failed photodash-discord.service 2>/dev/null || true
  systemctl restart photodash-discord.service 2>/dev/null || true
fi

echo
echo "Reset complete."
systemctl is-active photodash.service 2>/dev/null || true
systemctl is-active photodash-kiosk.service 2>/dev/null || true
systemctl is-active photodash-cliamp.service 2>/dev/null || true
