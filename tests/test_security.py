"""Security and validation regression tests."""

from __future__ import annotations

import subprocess
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

from tests.conftest import admin_post


def test_frame_survives_invalid_interval_in_db(app, admin_client):
    client, token = admin_client
    with app.app_context():
        from app.models import settings as settings_model

        settings_model.set("photo_interval_seconds", "not-a-number")

    assert client.get("/").status_code == 200
    assert client.get("/api/frame").status_code == 200


def test_settings_rejects_invalid_interval(admin_client):
    client, token = admin_client
    admin_post(
        client,
        token,
        "/admin/settings",
        data={
            "photo_interval_seconds": "99999",
            "frame_poll_seconds": "60",
            "storage_path": "",
            "weather_latitude": "",
            "weather_longitude": "",
            "weather_timezone": "UTC",
            "temperature_unit": "F",
        },
        follow_redirects=True,
    )
    frame = client.get("/api/frame").get_json()
    assert frame["photo_interval_seconds"] == 600


def test_settings_rejects_disallowed_storage_path(admin_client):
    client, token = admin_client
    res = admin_post(
        client,
        token,
        "/admin/settings",
        data={
            "photo_interval_seconds": "30",
            "frame_poll_seconds": "60",
            "storage_path": "/etc/photodash-disallowed-path-test",
            "weather_latitude": "",
            "weather_longitude": "",
            "weather_timezone": "UTC",
            "temperature_unit": "F",
        },
        follow_redirects=True,
    )
    assert b"allowed location" in res.data


def test_people_rejects_invalid_color(app, admin_client):
    client, token = admin_client
    res = admin_post(
        client,
        token,
        "/admin/people",
        data={"name": "Sam", "color": 'red" onmouseover="alert(1)'},
        follow_redirects=True,
    )
    assert b"#RRGGBB" in res.data
    with app.app_context():
        from app.models import people as people_model

        assert len(people_model.list_people()) == 0


def test_person_color_sanitized_in_frame_payload(app, admin_client):
    with app.app_context():
        from app.helpers import build_frame_payload, today_local
        from app.models import calendar as calendar_model
        from app.models import people as people_model

        pid = people_model.create_person("Pat", color='bad"color')
        calendar_model.create_entry(
            today_local().isoformat(),
            "chore",
            "Task",
            person_id=pid,
        )
        payload = build_frame_payload()
        today = today_local().isoformat()
        day = next(d for d in payload["days"] if d["date"] == today)
        assert day["entries"][0]["person_color"] is None


def test_photo_delete_searches_all_storage_roots(app, admin_client, tmp_path):
    client, token = admin_client
    primary = Path(app.config["STORAGE_PATH"])
    alt = tmp_path / "alt_storage"
    alt.mkdir()

    img = Image.new("RGB", (40, 80), color=(1, 2, 3))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    admin_post(
        client,
        token,
        "/admin/photos/upload",
        data={"photos": (buf, "portrait.jpg"), "csrf_token": token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    with app.app_context():
        from app.models import photos as photos_model

        row = photos_model.list_all()[0]
        filename = row["filename"]
        assert (primary / filename).exists()

    admin_post(
        client,
        token,
        "/admin/settings",
        data={
            "photo_interval_seconds": "30",
            "frame_poll_seconds": "60",
            "storage_path": str(alt),
            "weather_latitude": "",
            "weather_longitude": "",
            "weather_timezone": "UTC",
            "temperature_unit": "F",
        },
        follow_redirects=True,
    )
    assert (primary / filename).exists()
    assert not (alt / filename).exists()

    admin_post(client, token, f"/admin/photos/{row['id']}/delete", follow_redirects=True)
    assert not (primary / filename).exists()


def test_delete_rejects_absolute_filename(app, tmp_path):
    """Absolute filenames must not escape storage roots via Path join rules."""
    victim = tmp_path / "should-survive.txt"
    victim.write_text("keep me", encoding="utf-8")

    with app.app_context():
        from app.services.photo_pipeline import delete_stored_file

        delete_stored_file(str(victim.resolve()), app.config["STORAGE_PATH"])
        delete_stored_file("/etc/passwd", app.config["STORAGE_PATH"])
        delete_stored_file("../escape.jpg", app.config["STORAGE_PATH"])
        delete_stored_file(".hidden.jpg", app.config["STORAGE_PATH"])

    assert victim.exists()
    assert victim.read_text(encoding="utf-8") == "keep me"


def test_out_of_prefix_storage_path_not_added_to_allowlist(app):
    """A grandfathered DB path outside static prefixes must not widen the allowlist."""
    outside = Path("/etc/photodash-grandfather-test")
    with app.app_context():
        from app.models import settings as settings_model
        from app.validation import allowed_storage_roots, validate_storage_path_setting

        settings_model.set("storage_path", str(outside))
        roots = allowed_storage_roots(app.config["STORAGE_PATH"])
        assert outside.resolve() not in roots

        _, err = validate_storage_path_setting(
            str(outside / "child"),
            app.config["STORAGE_PATH"],
        )
        assert err is not None
        assert "allowed location" in err


def test_install_env_writer_quotes_special_chars(tmp_path):
    import shlex

    script = Path(__file__).resolve().parents[1] / "scripts" / "write_env_file.py"
    env_file = tmp_path / "photodash.env"
    secret = "abc$(echo PWNED)def"
    storage = "/mnt/usb/my photos"
    mixed = "it's a \"quote\" and $HOME and `id`"

    subprocess.run(
        [
            sys.executable,
            str(script),
            str(env_file),
            f"SECRET_KEY={secret}",
            f"PHOTODASH_STORAGE_PATH={storage}",
            f"MIXED={mixed}",
        ],
        check=True,
    )
    content = env_file.read_text(encoding="utf-8")
    assert "SECRET_KEY=" in content
    assert "$(echo PWNED)" in content  # preserved as data, not executed
    proc = subprocess.run(
        [
            "bash",
            "-c",
            f"set -a; source {shlex.quote(str(env_file))}; "
            'printf "SECRET=%s\\n" "$SECRET_KEY"; '
            'printf "MIXED=%s\\n" "$MIXED"; '
            'printf "STORAGE=%s\\n" "$PHOTODASH_STORAGE_PATH"',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = proc.stdout.splitlines()
    assert lines[0] == f"SECRET={secret}"
    assert lines[1] == f"MIXED={mixed}"
    assert lines[2] == f"STORAGE={storage}"
