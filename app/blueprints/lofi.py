"""CLIAMP visualizer band stream (SSE) for the frame lofi strip."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
from collections.abc import Iterator

from flask import Blueprint, Response, current_app, stream_with_context

from app.models import settings as settings_model

bp = Blueprint("lofi", __name__)
logger = logging.getLogger(__name__)

DEFAULT_VIS_FPS = 15
DEFAULT_CLIAMP_CONFIG_DIR = "/var/lib/photodash/cliamp"


def lofi_enabled() -> bool:
    installed = (settings_model.get("lofi_installed", "0") or "0").strip().lower()
    enabled = (settings_model.get("lofi_enabled", "0") or "0").strip().lower()
    return installed in ("1", "true", "yes", "on") and enabled in ("1", "true", "yes", "on")


def _cliamp_bin() -> str:
    configured = (current_app.config.get("CLIAMP_BIN") or "").strip()
    if configured:
        return configured
    env = (os.environ.get("PHOTODASH_CLIAMP_BIN") or "").strip()
    if env:
        return env
    return shutil.which("cliamp") or "cliamp"


def _cliamp_env() -> dict[str, str]:
    """Inherit the process env but point CLIAMP at the shared config dir."""
    env = os.environ.copy()
    config_dir = (
        (current_app.config.get("CLIAMP_CONFIG_DIR") or "").strip()
        or (os.environ.get("CLIAMP_CONFIG_DIR") or "").strip()
        or (os.environ.get("PHOTODASH_CLIAMP_CONFIG_DIR") or "").strip()
        or DEFAULT_CLIAMP_CONFIG_DIR
    )
    env["CLIAMP_CONFIG_DIR"] = config_dir
    return env


@bp.get("/api/visstream")
def visstream():
    if not lofi_enabled():
        return Response("lofi disabled\n", status=404, mimetype="text/plain")

    cliamp = _cliamp_bin()
    fps = int(current_app.config.get("CLIAMP_VIS_FPS") or DEFAULT_VIS_FPS)
    fps = max(1, min(30, fps))
    child_env = _cliamp_env()

    @stream_with_context
    def generate() -> Iterator[str]:
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                [cliamp, "visstream", f"--fps={fps}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=child_env,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                yield f"data: {line}\n\n"
        except FileNotFoundError:
            logger.warning("cliamp not found at %s", cliamp)
            yield 'data: {"ok":false,"error":"cliamp not found"}\n\n'
        except GeneratorExit:
            raise
        except Exception:
            logger.exception("visstream failed")
            yield 'data: {"ok":false,"error":"visstream failed"}\n\n'
        finally:
            if proc is not None and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1)
                except Exception:
                    logger.debug("failed to stop cliamp visstream", exc_info=True)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
