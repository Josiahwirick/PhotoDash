"""Kiosk liveness heartbeat written by the frame page (localhost only)."""

from __future__ import annotations

import os
import time
from pathlib import Path


def heartbeat_path() -> Path:
    env = (os.environ.get("PHOTODASH_KIOSK_HEARTBEAT_PATH") or "").strip()
    if env:
        return Path(env)
    return Path("/var/lib/photodash/kiosk-heartbeat")


def touch_heartbeat(
    *,
    dom_ok: bool = True,
    raf_seq: int = 0,
    photo_tick: int = 0,
    now: float | None = None,
) -> Path:
    """Update the heartbeat file for the kiosk watchdog.

    Format (one field per line)::
        <epoch>
        ok|fail
        raf=<int>
        tick=<int>
    """
    path = heartbeat_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = f"{(now if now is not None else time.time()):.3f}"
    status = "ok" if dom_ok else "fail"
    path.write_text(
        f"{stamp}\n{status}\nraf={int(raf_seq)}\ntick={int(photo_tick)}\n",
        encoding="utf-8",
    )
    return path


def read_heartbeat() -> dict[str, object] | None:
    """Parse the heartbeat file into a dict, or None if missing."""
    path = heartbeat_path()
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    if not lines:
        return None
    status = "ok"
    raf = 0
    tick = 0
    if len(lines) >= 2 and lines[1].strip() in {"ok", "fail"}:
        status = lines[1].strip()
    for line in lines[2:]:
        if line.startswith("raf="):
            try:
                raf = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("tick="):
            try:
                tick = int(line.split("=", 1)[1])
            except ValueError:
                pass
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {"status": status, "raf": raf, "tick": tick, "mtime": mtime}


def heartbeat_age_seconds(*, now: float | None = None) -> float | None:
    """Seconds since last heartbeat, or None if the file is missing."""
    path = heartbeat_path()
    if not path.is_file():
        return None
    current = now if now is not None else time.time()
    return max(0.0, current - path.stat().st_mtime)


def heartbeat_status() -> str | None:
    """Return 'ok', 'fail', or None if missing/unreadable."""
    data = read_heartbeat()
    if data is None:
        return None
    return str(data["status"])
