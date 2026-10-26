#!/usr/bin/env bash
# Deploy durability stack to the PhotoDash Pi (from the PhotoDash repo root).
#
#   ./scripts/deploy-durability.sh
#   ./scripts/deploy-durability.sh 192.168.4.50
#   PHOTODASH_SSH_KEY=~/.ssh/id_ed25519_wirick ./scripts/deploy-durability.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="${PHOTODASH_SSH_KEY:-$HOME/.ssh/id_ed25519_wirick}"
TARGET_HOST="${1:-}"
USER_HOST="pi@wirick-pictures"

ssh_base=(ssh -o IdentitiesOnly=yes -i "$KEY" -o ConnectTimeout=4 -o BatchMode=yes)
rsync_rsh="ssh -o IdentitiesOnly=yes -i $KEY -o ConnectTimeout=12 -o BatchMode=yes"

pick_host() {
  local candidates=()
  if [[ -n "$TARGET_HOST" ]]; then
    candidates+=("$TARGET_HOST")
  fi
  candidates+=(wirick-pictures 192.168.4.50 192.168.4.162 100.79.121.116)
  local h
  for h in "${candidates[@]}"; do
    if ping -c1 -W1 "$h" >/dev/null 2>&1 \
      || [[ "$h" == *wirick* ]]; then
      if "${ssh_base[@]}" -o HostName="$h" "$USER_HOST" 'echo ok' >/dev/null 2>&1; then
        echo "$h"
        return 0
      fi
    fi
  done
  # Always try hostname + Tailscale even if ping failed (ICMP may be blocked).
  for h in wirick-pictures 100.79.121.116; do
    if "${ssh_base[@]}" -o HostName="$h" "$USER_HOST" 'echo ok' >/dev/null 2>&1; then
      echo "$h"
      return 0
    fi
  done
  return 1
}

echo "==> Waiting for Pi (power-cycle if the display is still frozen) ..."
HOST=""
for i in $(seq 1 180); do
  if HOST="$(pick_host)"; then
    echo "    reachable via $HOST"
    break
  fi
  if (( i % 6 == 0 )); then
    printf '    still unreachable (%sm elapsed)\n' "$((i / 6))"
  fi
  sleep 5
done
[[ -n "$HOST" ]] || { echo "Pi never came back after 15+ minutes." >&2; exit 1; }

ssh_cmd=("${ssh_base[@]}" -o HostName="$HOST" "$USER_HOST")
rsync_rsh="$rsync_rsh -o HostName=$HOST"

echo "==> Syncing to $USER_HOST ($HOST)"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data/' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' --exclude '.env' \
  -e "$rsync_rsh" \
  "$ROOT/" "$USER_HOST:~/photodash/"

echo "==> Installing durability stack"
"${ssh_cmd[@]}" 'sudo bash -s' <<'REMOTE'
set -euo pipefail
SRC=/home/pi/photodash
APP=/opt/photodash

if [[ -d "$APP/discord_bot/.venv" ]]; then
  mv "$APP/discord_bot/.venv" /tmp/photodash-discord-venv.bak
fi
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data/' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.env' \
  "$SRC/" "$APP/"
if [[ -d /tmp/photodash-discord-venv.bak ]]; then
  mkdir -p "$APP/discord_bot"
  mv /tmp/photodash-discord-venv.bak "$APP/discord_bot/.venv"
fi
chown -R photodash:photodash "$APP"

install -m 755 "$SRC/scripts/photodash-reset.sh" /usr/local/sbin/photodash-reset
install -m 755 "$SRC/scripts/photodash-kiosk-watchdog.sh" /usr/local/sbin/photodash-kiosk-watchdog
install -m 644 "$SRC/deploy/photodash-kiosk-watchdog.service" /etc/systemd/system/photodash-kiosk-watchdog.service
install -m 755 "$SRC/deploy/xinitrc" /etc/photodash/xinitrc
install -m 644 "$SRC/deploy/photodash.service" /etc/systemd/system/photodash.service

kiosk_user=pi
kiosk_home=/home/pi
kiosk_uid=$(id -u pi)
sed -e "s|KIOSK_USER|${kiosk_user}|g" -e "s|KIOSK_HOME|${kiosk_home}|g" \
  "$SRC/deploy/photodash-kiosk.service" > /etc/systemd/system/photodash-kiosk.service
if systemctl cat photodash-cliamp.service >/dev/null 2>&1 \
  || [[ -f /etc/systemd/system/photodash-cliamp.service ]]; then
  sed -e "s|KIOSK_USER|${kiosk_user}|g" -e "s|KIOSK_HOME|${kiosk_home}|g" -e "s|KIOSK_UID|${kiosk_uid}|g" \
    "$SRC/deploy/photodash-cliamp.service" > /etc/systemd/system/photodash-cliamp.service
fi

if apt-cache show earlyoom >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq earlyoom || true
fi
if [[ -f "$SRC/deploy/earlyoom.default" ]] && command -v earlyoom >/dev/null 2>&1; then
  install -m 644 "$SRC/deploy/earlyoom.default" /etc/default/earlyoom
  systemctl enable --now earlyoom.service || true
fi

install -d /etc/systemd/system.conf.d
install -m 644 "$SRC/deploy/photodash-runtime-watchdog.conf" \
  /etc/systemd/system.conf.d/photodash-watchdog.conf
modprobe bcm2835_wdt 2>/dev/null || modprobe raspberrypi_wdt 2>/dev/null || true
for cfg in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$cfg" ]] && ! grep -q '^dtparam=watchdog=on' "$cfg"; then
    echo 'dtparam=watchdog=on' >> "$cfg"
    echo "NOTE: enabled dtparam=watchdog=on in $cfg (next reboot)"
  fi
done

mkdir -p /var/lib/photodash
chown photodash:photodash /var/lib/photodash

systemctl daemon-reload
systemctl disable --now photodash-kiosk-watchdog.timer 2>/dev/null || true
rm -f /etc/systemd/system/photodash-kiosk-watchdog.timer
systemctl enable --now photodash-kiosk-watchdog.service
systemctl restart photodash.service
sleep 3
if ! systemctl is-active --quiet photodash; then
  systemctl kill -s SIGKILL photodash.service 2>/dev/null || true
  systemctl reset-failed photodash.service
  systemctl start photodash.service
  sleep 3
fi
if command -v photodash-reset >/dev/null 2>&1; then
  photodash-reset --kiosk-only || systemctl restart photodash-kiosk.service || true
else
  systemctl restart photodash-kiosk.service || true
fi
# Restart cliamp under new MemoryMax if present
if systemctl is-enabled photodash-cliamp.service >/dev/null 2>&1; then
  systemctl restart photodash-cliamp.service || true
fi
sleep 12

echo "=== status ==="
systemctl is-active photodash photodash-kiosk photodash-kiosk-watchdog 2>/dev/null || true
systemctl is-active earlyoom 2>/dev/null || echo "earlyoom: not active"
systemctl is-enabled photodash-kiosk-watchdog 2>/dev/null || true
free -h | head -2
curl -sf http://127.0.0.1:8080/health; echo
sleep 18
echo "=== heartbeat ==="
cat /var/lib/photodash/kiosk-heartbeat 2>/dev/null || echo "(no heartbeat yet)"
journalctl -u photodash-kiosk-watchdog -n 25 --no-pager
REMOTE

echo "==> Deploy complete on $HOST"
