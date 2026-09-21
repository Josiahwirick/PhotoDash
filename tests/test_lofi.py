"""Tests for CLIAMP visstream SSE proxy."""

from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

from app.models import settings as settings_model


def _install_fake_cliamp(bin_dir: Path) -> Path:
    script = bin_dir / "cliamp"
    script.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            # Fake cliamp for PhotoDash tests.
            if [ "$1" = "visstream" ]; then
              echo '{"ok":true,"visualizer":"Bars","bands":[0.1,0.2,0.3,0.4,0.5,0.4,0.3,0.2,0.1,0.05]}'
              echo '{"ok":true,"visualizer":"Bars","bands":[0.2,0.3,0.4,0.5,0.6,0.5,0.4,0.3,0.2,0.1]}'
              exit 0
            fi
            echo "unexpected: $*" >&2
            exit 1
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_visstream_sse_streams_bands(app, client, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_cliamp(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    app.config["CLIAMP_BIN"] = str(bin_dir / "cliamp")

    with app.app_context():
        settings_model.set("lofi_installed", "1")
        settings_model.set("lofi_enabled", "1")

    res = client.get("/api/visstream")
    assert res.status_code == 200
    assert res.mimetype == "text/event-stream"
    body = res.get_data(as_text=True)
    assert "data: " in body
    assert '"bands"' in body
    assert "0.5" in body


def test_visstream_disabled_returns_404(app, client):
    with app.app_context():
        settings_model.set("lofi_installed", "1")
        settings_model.set("lofi_enabled", "0")

    res = client.get("/api/visstream")
    assert res.status_code == 404


def test_visstream_not_installed_returns_404(app, client):
    with app.app_context():
        settings_model.set("lofi_installed", "0")
        settings_model.set("lofi_enabled", "1")

    res = client.get("/api/visstream")
    assert res.status_code == 404


def test_frame_includes_lofi_strip_when_enabled(app, client):
    with app.app_context():
        settings_model.set("lofi_installed", "1")
        settings_model.set("lofi_enabled", "1")

    res = client.get("/")
    assert res.status_code == 200
    assert b'id="lofi-strip"' in res.data
    assert b"lofi.js" in res.data
    assert b'data-lofi="1"' in res.data
    assert b"calendar--lofi" in res.data


def test_frame_hides_lofi_strip_when_disabled(app, client):
    with app.app_context():
        settings_model.set("lofi_installed", "1")
        settings_model.set("lofi_enabled", "0")

    res = client.get("/")
    assert res.status_code == 200
    assert b'id="lofi-strip"' not in res.data
    assert b"lofi.js" not in res.data
    assert b'data-lofi="0"' in res.data
    assert b"calendar--lofi" not in res.data


def test_frame_hides_lofi_when_not_installed(app, client):
    with app.app_context():
        settings_model.set("lofi_installed", "0")
        settings_model.set("lofi_enabled", "1")

    res = client.get("/")
    assert res.status_code == 200
    assert b'id="lofi-strip"' not in res.data
    assert b"calendar--lofi" not in res.data


def test_frame_includes_font_boost(app, client):
    with app.app_context():
        settings_model.set("calendar_font_boost", "8")

    res = client.get("/")
    assert res.status_code == 200
    assert b"--cal-font-boost: 8px" in res.data
