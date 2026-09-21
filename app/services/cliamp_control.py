"""Control the headless CLIAMP lofi daemon via IPC."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

from flask import current_app

logger = logging.getLogger(__name__)

DEFAULT_CLIAMP_CONFIG_DIR = "/var/lib/photodash/cliamp"


def _cliamp_bin() -> str:
    configured = ""
    try:
        configured = (current_app.config.get("CLIAMP_BIN") or "").strip()
    except RuntimeError:
        configured = ""
    if configured:
        return configured
    env = (os.environ.get("PHOTODASH_CLIAMP_BIN") or "").strip()
    if env:
        return env
    return shutil.which("cliamp") or "cliamp"


def _cliamp_env() -> dict[str, str]:
    env = os.environ.copy()
    config_dir = ""
    try:
        config_dir = (current_app.config.get("CLIAMP_CONFIG_DIR") or "").strip()
    except RuntimeError:
        config_dir = ""
    config_dir = (
        config_dir
        or (os.environ.get("CLIAMP_CONFIG_DIR") or "").strip()
        or (os.environ.get("PHOTODASH_CLIAMP_CONFIG_DIR") or "").strip()
        or DEFAULT_CLIAMP_CONFIG_DIR
    )
    env["CLIAMP_CONFIG_DIR"] = config_dir
    return env


def stream_control(command: str) -> dict[str, str]:
    """
    Pause or resume the lofi stream.

    command: "stop" | "start"  (maps to cliamp pause / play)
    """
    cmd = (command or "").strip().lower()
    if cmd not in ("stop", "start"):
        raise ValueError("Stream command must be 'stop' or 'start'.")

    cliamp_cmd = "pause" if cmd == "stop" else "play"
    try:
        completed = subprocess.run(
            [_cliamp_bin(), cliamp_cmd],
            capture_output=True,
            text=True,
            timeout=10,
            env=_cliamp_env(),
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("cliamp is not installed on this machine.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Timed out talking to the lofi stream.") from exc

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        logger.warning("cliamp %s failed: %s", cliamp_cmd, err)
        if "connect" in err.lower() or "dial" in err.lower() or "no such file" in err.lower():
            raise ValueError(
                "Lofi stream is not running (is photodash-cliamp active?)."
            )
        raise ValueError(err or f"Could not {cmd} the stream.")

    state = "stopped" if cmd == "stop" else "playing"
    return {"command": cmd, "state": state}
