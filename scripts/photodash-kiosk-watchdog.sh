#!/usr/bin/env bash
# Continuous PhotoDash kiosk / lofi durability watchdog.
#
# Runs as a long-lived systemd service (photodash-kiosk-watchdog.service).
# Detects freezes that leave Chromium "alive" but stuck, memory pressure that
# precedes hard lockups, and dead CLIAMP audio — then soft-resets without
# rebooting the Pi.
#
#   sudo photodash-kiosk-watchdog            # one check (compat)
#   sudo photodash-kiosk-watchdog --daemon   # loop forever

set -euo pipefail

STATE_DIR="${PHOTODASH_STATE_DIR:-/var/lib/photodash}"
HEARTBEAT_FILE="${PHOTODASH_KIOSK_HEARTBEAT_PATH:-$STATE_DIR/kiosk-heartbeat}"
STATE_FILE="$STATE_DIR/kiosk-watchdog-state"
COOLDOWN_FILE="$STATE_DIR/kiosk-watchdog-last-restart"
LOCK_FILE="$STATE_DIR/kiosk-watchdog.lock"
RESET_BIN="${PHOTODASH_RESET_BIN:-/usr/local/sbin/photodash-reset}"

HEARTBEAT_MAX_AGE="${PHOTODASH_KIOSK_HEARTBEAT_MAX_AGE:-60}"
BOOT_GRACE="${PHOTODASH_KIOSK_BOOT_GRACE:-120}"
# Soft cooldown between identical recoveries when healthy after restart.
RESTART_COOLDOWN="${PHOTODASH_KIOSK_RESTART_COOLDOWN:-300}"
DAEMON_INTERVAL="${PHOTODASH_KIOSK_WATCHDOG_INTERVAL:-30}"
# MemAvailable below this (kB) → full reset + pause lofi.
# Tuned for Raspberry Pi 3B+ 1GB (~906 MiB total).
MEM_FLOOR_KB="${PHOTODASH_KIOSK_MEM_FLOOR_KB:-102400}"  # 100 MiB
# 1-minute load average above this for 2 checks → full reset.
LOAD_CEILING="${PHOTODASH_KIOSK_LOAD_CEILING:-6}"
# Chromium PSS ceilings — only act when MemAvailable is also tight (see
# resource_pressure). Avoid restart loops on healthy ~400 MiB Chromium.
CHROMIUM_RSS_CEILING_KB="${PHOTODASH_KIOSK_CHROMIUM_RSS_KB:-600000}"  # ~585 MiB PSS
CHROMIUM_RSS_HARD_KB="${PHOTODASH_KIOSK_CHROMIUM_RSS_HARD_KB:-700000}"  # ~685 MiB PSS
# After this many failed recoveries in a row, reboot (last resort before brick).
REBOOT_AFTER_FAILS="${PHOTODASH_KIOSK_REBOOT_AFTER:-8}"

log() { printf 'photodash-kiosk-watchdog: %s\n' "$*"; }

kiosk_user() {
  local u
  u="$(systemctl show -p User --value photodash-kiosk.service 2>/dev/null || true)"
  if [[ -n "$u" && "$u" != "-" ]]; then
    printf '%s\n' "$u"
    return
  fi
  if id pi >/dev/null 2>&1; then echo pi; else echo root; fi
}

kiosk_home() { getent passwd "$(kiosk_user)" | cut -d: -f6; }

now_epoch() { date +%s; }

file_age() {
  local path="$1"
  [[ -f "$path" ]] || { echo 999999; return; }
  local mtime
  mtime="$(stat -c %Y "$path" 2>/dev/null || echo 0)"
  echo $(( $(now_epoch) - mtime ))
}

read_state() {
  LAST_RAF=0
  LAST_TICK=0
  STUCK_RAF_CHECKS=0
  PRESSURE_CHECKS=0
  FAIL_STREAK=0
  LOFI_PAUSED=0
  [[ -f "$STATE_FILE" ]] || return 0
  # shellcheck disable=SC1090
  source "$STATE_FILE" 2>/dev/null || true
}

write_state() {
  mkdir -p "$STATE_DIR"
  cat >"$STATE_FILE" <<EOF
LAST_RAF=${LAST_RAF:-0}
LAST_TICK=${LAST_TICK:-0}
STUCK_RAF_CHECKS=${STUCK_RAF_CHECKS:-0}
PRESSURE_CHECKS=${PRESSURE_CHECKS:-0}
FAIL_STREAK=${FAIL_STREAK:-0}
LOFI_PAUSED=${LOFI_PAUSED:-0}
EOF
}

mark_restart() {
  mkdir -p "$STATE_DIR"
  date -u +%Y-%m-%dT%H:%M:%SZ >"$COOLDOWN_FILE"
  rm -f "$HEARTBEAT_FILE"
  # Counter will restart at 0 after the page reloads.
  LAST_RAF=0
  LAST_TICK=0
  STUCK_RAF_CHECKS=0
}

in_boot_grace() {
  [[ "$(file_age "$COOLDOWN_FILE")" -lt "$BOOT_GRACE" ]]
}

chromium_boot_grace() {
  local pid etime
  pid="$(pgrep -f '[c]hromium.*--app=http://127\.0\.0\.1:8080' | head -1 || true)"
  [[ -n "$pid" ]] || return 1
  etime="$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ' || echo 9999)"
  [[ "${etime:-9999}" -lt "$BOOT_GRACE" ]]
}

chromium_kiosk_running() {
  pgrep -f '[c]hromium.*(kiosk|--app=http://127\.0\.0\.1:8080)' >/dev/null 2>&1
}

xorg_running() {
  pgrep -x Xorg >/dev/null 2>&1 || pgrep -f '[X]org :0' >/dev/null 2>&1
}

content_renderer_running() {
  local pid cmdline
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
    [[ -n "$cmdline" ]] || continue
    if [[ "$cmdline" != *top-chrome-webui* ]]; then
      return 0
    fi
  done < <(pgrep -f '[c]hromium.*--type=renderer' 2>/dev/null || true)
  return 1
}

# Legacy fbi slideshow must not share the console with Chromium.
kill_legacy_fbi() {
  if pgrep -x fbi >/dev/null 2>&1; then
    log "killing legacy fbi slideshow (competes with Chromium)"
    pkill -x fbi 2>/dev/null || true
    sleep 0.5
    pkill -9 -x fbi 2>/dev/null || true
  fi
}

x_display_ok() {
  local user home
  user="$(kiosk_user)"
  home="$(kiosk_home)"
  [[ -n "$home" ]] || return 1
  timeout 4 sudo -u "$user" env \
    DISPLAY=:0 XAUTHORITY="${home}/.Xauthority" HOME="$home" \
    xset q >/dev/null 2>&1
}

app_healthy() {
  curl -sf --max-time 4 http://127.0.0.1:8080/health >/dev/null 2>&1
}

cliamp_should_run() {
  systemctl cat photodash-cliamp.service >/dev/null 2>&1 \
    && systemctl is-enabled photodash-cliamp.service >/dev/null 2>&1
}

cliamp_ok() {
  pgrep -x cliamp >/dev/null 2>&1 || return 1
  [[ -S /var/lib/photodash/cliamp/cliamp.sock ]] || return 1
  return 0
}

mem_available_kb() {
  awk '/MemAvailable:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 999999
}

load_1m() {
  awk '{print $1}' /proc/loadavg
}

chromium_rss_kb() {
  # Prefer PSS (proportional set size) — RSS sum massively double-counts shared
  # Chromium mappings on a multi-process browser (~1GB RSS ≈ ~350MB real).
  local total=0 pss pid
  local any=0
  for pid in $(pgrep -x chromium 2>/dev/null || true); do
    pss="$(awk '/^Pss:/ {print $2; exit}' "/proc/$pid/smaps_rollup" 2>/dev/null || true)"
    if [[ -n "$pss" ]]; then
      total=$((total + pss))
      any=1
    fi
  done
  if [[ "$any" -eq 1 ]]; then
    echo "$total"
    return
  fi
  # Fallback: RSS sum (inflated) if smaps_rollup unavailable.
  while read -r pss; do
    [[ -n "$pss" ]] || continue
    total=$((total + pss))
  done < <(ps -C chromium -o rss= 2>/dev/null || true)
  echo "$total"
}

parse_heartbeat() {
  HB_STATUS="missing"
  HB_RAF=0
  HB_TICK=0
  HB_AGE=999999
  [[ -f "$HEARTBEAT_FILE" ]] || return 1
  HB_AGE="$(file_age "$HEARTBEAT_FILE")"
  local line
  while IFS= read -r line; do
    case "$line" in
      ok|fail) HB_STATUS="$line" ;;
      raf=*) HB_RAF="${line#raf=}" ;;
      tick=*) HB_TICK="${line#tick=}" ;;
    esac
  done <"$HEARTBEAT_FILE"
  HB_RAF="${HB_RAF:-0}"
  HB_TICK="${HB_TICK:-0}"
  return 0
}

# Returns 0 if frame looks live.
heartbeat_live() {
  if in_boot_grace || chromium_boot_grace; then
    return 0
  fi
  parse_heartbeat || return 1
  [[ "$HB_STATUS" == "ok" ]] || return 1
  [[ "$HB_AGE" -le "$HEARTBEAT_MAX_AGE" ]] || return 1
  return 0
}

# Returns 0 (ok) if raf is advancing; 1 if stuck.
raf_advancing() {
  if in_boot_grace || chromium_boot_grace; then
    STUCK_RAF_CHECKS=0
    return 0
  fi
  parse_heartbeat || return 1
  # Page reload / kiosk restart resets the counter — not a freeze.
  if [[ "$HB_RAF" -lt "${LAST_RAF:-0}" ]]; then
    log "raf_seq reset ${LAST_RAF}->${HB_RAF} (page reload); clearing stuck"
    LAST_RAF="$HB_RAF"
    LAST_TICK="$HB_TICK"
    STUCK_RAF_CHECKS=0
    return 0
  fi
  if [[ "$HB_RAF" -gt "${LAST_RAF:-0}" ]]; then
    LAST_RAF="$HB_RAF"
    LAST_TICK="$HB_TICK"
    STUCK_RAF_CHECKS=0
    return 0
  fi
  # Heartbeat file must be fresh — otherwise stale/missing already covers it.
  if [[ "$HB_AGE" -le "$HEARTBEAT_MAX_AGE" && "$HB_STATUS" == "ok" ]]; then
    STUCK_RAF_CHECKS=$((STUCK_RAF_CHECKS + 1))
    log "raf_seq stuck at ${HB_RAF} (checks=${STUCK_RAF_CHECKS})"
    # ~2.5 min at 30s interval — avoid thrashing on a single missed HB write.
    [[ "$STUCK_RAF_CHECKS" -ge 5 ]] && return 1
    return 0
  fi
  return 1
}

resource_pressure() {
  local mem load rss
  mem="$(mem_available_kb)"
  load="$(load_1m)"
  rss="$(chromium_rss_kb)"
  local pressure=0
  local hard=0
  if [[ "$mem" -lt "$MEM_FLOOR_KB" ]]; then
    log "memory pressure: MemAvailable=${mem}kB < ${MEM_FLOOR_KB}kB"
    pressure=1
  fi
  if awk -v l="$load" -v c="$LOAD_CEILING" 'BEGIN { exit !(l+0 >= c+0) }'; then
    log "load pressure: load1=${load} >= ${LOAD_CEILING}"
    pressure=1
  fi
  # Chromium PSS alone is noisy on a 1GB Pi — only count it when RAM is also low.
  if [[ "$rss" -gt "$CHROMIUM_RSS_HARD_KB" && "$mem" -lt $((MEM_FLOOR_KB * 2)) ]]; then
    log "chromium PSS HARD: ${rss}kB with mem=${mem}kB"
    hard=1
    pressure=1
  elif [[ "$rss" -gt "$CHROMIUM_RSS_CEILING_KB" && "$mem" -lt $((MEM_FLOOR_KB * 3)) ]]; then
    log "chromium PSS pressure: ${rss}kB with mem=${mem}kB"
    pressure=1
  fi
  if [[ -r /proc/pressure/memory ]]; then
    local someavg
    someavg="$(awk -F'[= ]' '/^some / {print $5; exit}' /proc/pressure/memory 2>/dev/null || echo 0)"
    if awk -v a="${someavg:-0}" 'BEGIN { exit !(a+0 >= 40.0) }'; then
      log "PSI memory some avg10=${someavg} >= 40%"
      pressure=1
    fi
  fi
  if [[ "$hard" -eq 1 ]]; then
    PRESSURE_CHECKS=2
    return 0
  fi
  if [[ "$pressure" -eq 1 ]]; then
    PRESSURE_CHECKS=$((PRESSURE_CHECKS + 1))
    [[ "$PRESSURE_CHECKS" -ge 3 ]] && return 0
    return 1
  fi
  PRESSURE_CHECKS=0
  return 1
}

should_skip_restart() {
  local age
  age="$(file_age "$COOLDOWN_FILE")"
  if [[ "$age" -lt "$BOOT_GRACE" ]]; then
    log "skip restart — boot grace (${age}s)"
    return 0
  fi
  if chromium_boot_grace; then
    log "skip restart — Chromium still starting"
    return 0
  fi
  if [[ "$age" -lt "$RESTART_COOLDOWN" ]]; then
    if heartbeat_live && content_renderer_running; then
      log "skip restart — cooldown + healthy"
      return 0
    fi
    log "cooldown overridden — still unhealthy (${age}s since last restart)"
  fi
  return 1
}

pause_lofi() {
  if ! cliamp_should_run; then return 0; fi
  log "pausing lofi to relieve memory/CPU pressure"
  systemctl stop photodash-cliamp.service 2>/dev/null || true
  pkill -x cliamp 2>/dev/null || true
  LOFI_PAUSED=1
}

resume_lofi_if_paused() {
  [[ "${LOFI_PAUSED:-0}" -eq 1 ]] || return 0
  if ! cliamp_should_run; then
    LOFI_PAUSED=0
    return 0
  fi
  # Only resume after a stretch of healthy checks (FAIL_STREAK cleared).
  if [[ "${FAIL_STREAK:-0}" -eq 0 && "${PRESSURE_CHECKS:-0}" -eq 0 ]]; then
    log "resuming lofi after healthy period"
    systemctl start photodash-cliamp.service 2>/dev/null || true
    LOFI_PAUSED=0
  fi
}

do_recover() {
  local reason="$1"
  local scope="${2:-kiosk}"
  if should_skip_restart "$reason"; then
    return 0
  fi
  FAIL_STREAK=$((FAIL_STREAK + 1))
  log "recovering scope=${scope} streak=${FAIL_STREAK} — ${reason}"
  mark_restart
  STUCK_RAF_CHECKS=0

  if [[ ! -x "$RESET_BIN" ]]; then
    log "ERROR: $RESET_BIN missing"
    write_state
    return 1
  fi

  # Escalation: 1=kiosk, 2+=full, and pause lofi under pressure / repeated fails.
  if [[ "$scope" == "pressure" || "$FAIL_STREAK" -ge 2 ]]; then
    pause_lofi
    "$RESET_BIN" || true
  elif [[ "$scope" == "all" ]]; then
    "$RESET_BIN" || true
  elif [[ "$scope" == "lofi" ]]; then
    "$RESET_BIN" --lofi-only || true
  else
    if [[ "$FAIL_STREAK" -ge 3 ]]; then
      pause_lofi
      "$RESET_BIN" || true
    else
      "$RESET_BIN" --kiosk-only || true
    fi
  fi

  # Soft recovery keeps failing while the box is still alive → reboot rather
  # than leave a white/frozen frame until someone power-cycles.
  if [[ "$FAIL_STREAK" -ge "$REBOOT_AFTER_FAILS" ]]; then
    log "FAIL_STREAK=${FAIL_STREAK} >= ${REBOOT_AFTER_FAILS} — scheduling reboot in 15s"
    write_state
    # Detach so journald flushes the message before reboot.
    ( sleep 15; /sbin/reboot ) >/dev/null 2>&1 &
    return 0
  fi
  write_state
}

check_once() {
  read_state

  if ! systemctl cat photodash-kiosk.service >/dev/null 2>&1; then
    return 0
  fi
  if ! systemctl is-enabled photodash-kiosk.service >/dev/null 2>&1; then
    return 0
  fi

  # Always reclaim RAM from the old console slideshow if it respawned.
  kill_legacy_fbi

  local recovered=0

  if ! systemctl is-active --quiet photodash-kiosk.service; then
    do_recover "photodash-kiosk inactive" kiosk
    recovered=1
  elif ! app_healthy; then
    do_recover "PhotoDash /health failed" all
    recovered=1
  elif ! xorg_running; then
    do_recover "Xorg not running" kiosk
    recovered=1
  elif ! chromium_kiosk_running; then
    do_recover "Chromium kiosk process missing" kiosk
    recovered=1
  elif ! x_display_ok; then
    if in_boot_grace || chromium_boot_grace; then
      log "X display not ready (boot grace)"
    else
      do_recover "X display :0 unresponsive" kiosk
      recovered=1
    fi
  elif ! content_renderer_running; then
    if in_boot_grace || chromium_boot_grace; then
      log "content renderer not up (boot grace)"
    else
      do_recover "Chromium content renderer missing" kiosk
      recovered=1
    fi
  elif ! heartbeat_live; then
    do_recover "frame heartbeat stale/missing/DOM-invalid" kiosk
    recovered=1
  elif ! raf_advancing; then
    # Soft kiosk restart only — full stack reset was thrashing the Pi 3B+.
    do_recover "frame rAF sequence frozen (main thread/compositor wedged)" kiosk
    recovered=1
  elif resource_pressure; then
    do_recover "system resource pressure (mem/load/chromium RSS)" pressure
    recovered=1
  fi

  if [[ "$recovered" -eq 0 ]]; then
    # Healthy path
    if [[ "${FAIL_STREAK:-0}" -gt 0 ]]; then
      log "healthy — clearing fail streak (was ${FAIL_STREAK})"
    fi
    FAIL_STREAK=0
    resume_lofi_if_paused
    parse_heartbeat || true
    # Still verify cliamp if it should be running and we didn't pause it.
    if [[ "${LOFI_PAUSED:-0}" -eq 0 ]] && cliamp_should_run && ! cliamp_ok; then
      do_recover "CLIAMP process/socket missing" lofi
    else
      log "ok (raf=${HB_RAF:-?} tick=${HB_TICK:-?} mem=$(mem_available_kb)kB load=$(load_1m))"
    fi
  fi

  write_state
}

daemon_loop() {
  log "daemon starting (interval=${DAEMON_INTERVAL}s)"
  while true; do
    # Don't let a single check abort the daemon.
    set +e
    (
      flock -n 9 || exit 0
      check_once
    ) 9>"$LOCK_FILE"
    set -e
    sleep "$DAEMON_INTERVAL"
  done
}

main() {
  mkdir -p "$STATE_DIR"
  if [[ "${1:-}" == "--daemon" ]]; then
    daemon_loop
    exit 0
  fi
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log "another watchdog run in progress; exiting"
    exit 0
  fi
  check_once
}

main "$@"
