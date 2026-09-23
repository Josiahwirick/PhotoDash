"""Soft-reset PhotoDash services (kiosk / CLIAMP) without rebooting."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

RESET_BIN = "/usr/local/sbin/photodash-reset"


def reset_frame(*, scope: str = "all") -> dict[str, str]:
    """
    Run the privileged photodash-reset helper via sudo.

    scope: "all" | "lofi" | "kiosk"
    """
    mode = (scope or "all").strip().lower()
    args = [RESET_BIN]
    if mode in ("lofi", "lofi-only", "stream"):
        args.append("--lofi-only")
        label = "lofi"
    elif mode in ("kiosk", "kiosk-only", "frame"):
        args.append("--kiosk-only")
        label = "kiosk"
    else:
        label = "all"

    if not os.path.isfile(RESET_BIN):
        raise ValueError(
            "Reset helper is not installed. On the Pi run: "
            "sudo install -m 755 scripts/photodash-reset.sh /usr/local/sbin/photodash-reset"
        )

    sudo = shutil.which("sudo") or "/usr/bin/sudo"
    try:
        completed = subprocess.run(
            [sudo, "-n", *args],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Reset timed out.") from exc

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        logger.warning("photodash-reset failed: %s", err)
        if "password" in err.lower() or "a password is required" in err.lower():
            raise ValueError(
                "Reset needs passwordless sudo for photodash. "
                "Installer should install /etc/sudoers.d/photodash-reset."
            )
        raise ValueError(err or "Reset failed.")

    return {"scope": label, "status": "ok"}
