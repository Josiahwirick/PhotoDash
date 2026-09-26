"""Tests for POST /api/webhook."""

from __future__ import annotations

from app.models import calendar as calendar_model
from app.models import people as people_model
from app.models import settings as settings_model
from tests.conftest import admin_post


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_webhook_unauthorized(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
    res = client.post("/api/webhook", json={"text": "add person A"})
    assert res.status_code == 401


def test_webhook_create_person_structured(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
    res = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"intent": "person", "name": "Estelle", "color": "#7cb89a"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["action"] == "create_person"
    assert data["result"]["name"] == "Estelle"
    with app.app_context():
        assert people_model.get_person_by_name("Estelle") is not None


def test_webhook_create_person_duplicate(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
        people_model.create_person("Estelle")
    res = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"text": "add person Estelle"},
    )
    assert res.status_code == 409


def test_webhook_create_entry_structured(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
        people_model.create_person("Estelle")
    res = client.post(
        "/api/webhook",
        headers={**_auth_headers("secret-token"), "X-PhotoDash-Token": "secret-token"},
        json={
            "intent": "calendar",
            "entry_type": "chore",
            "entry_date": "2026-09-20",
            "text": "take out trash",
            "person": "Estelle",
        },
    )
    # Prefer Authorization; X-PhotoDash-Token also works alone — here both set
    assert res.status_code == 200
    data = res.get_json()
    assert data["action"] == "create_entry"
    assert data["result"]["person_name"] == "Estelle"
    with app.app_context():
        rows = calendar_model.list_for_dates(["2026-09-20"])
        assert any(r["text"] == "take out trash" for r in rows)


def test_webhook_create_entry_unknown_person(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
    res = client.post(
        "/api/webhook",
        headers={"X-PhotoDash-Token": "secret-token"},
        json={"text": "chore tomorrow: trash for Nobody"},
    )
    assert res.status_code == 400
    assert "No person" in res.get_json()["error"]


def test_webhook_free_text_entry(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
        people_model.create_person("Caspar")
        settings_model.set("weather_timezone", "America/Denver")
    res = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"text": "reminder today pack lunch for Caspar"},
    )
    assert res.status_code == 200
    assert res.get_json()["action"] == "create_entry"


def test_webhook_x_token_header(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
    res = client.post(
        "/api/webhook",
        headers={"X-PhotoDash-Token": "secret-token"},
        json={"text": "add person Kiddo"},
    )
    assert res.status_code == 200


def test_webhook_stream_stop_start(client, app, tmp_path, monkeypatch):
    import os
    import stat
    import textwrap

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "cliamp"
    script.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            echo "ok $1" >&2
            exit 0
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
        app.config["CLIAMP_BIN"] = str(script)

    stop = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"text": "stop stream"},
    )
    assert stop.status_code == 200
    assert stop.get_json()["action"] == "stream_control"
    assert stop.get_json()["result"]["state"] == "stopped"

    start = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"intent": "stream", "command": "start"},
    )
    assert start.status_code == 200
    assert start.get_json()["result"]["state"] == "playing"


def test_webhook_delete_entry(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
        settings_model.set("weather_timezone", "America/Denver")
        people_model.create_person("Estelle")
        from app.helpers import today_local
        from datetime import timedelta

        day = (today_local() + timedelta(days=1)).isoformat()
        calendar_model.create_entry(day, "chore", "take out trash", person_id=1)

    res = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"text": "delete chore tomorrow: take out trash for Estelle"},
    )
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert data["action"] == "delete_entry"
    assert data["result"]["deleted"] == 1
    with app.app_context():
        assert calendar_model.find_entries(text_query="take out trash") == []


def test_admin_calendar_delete(admin_client, app):
    client, token = admin_client
    with app.app_context():
        from app.helpers import today_local

        entry_id = calendar_model.create_entry(
            today_local().isoformat(), "reminder", "pack lunch"
        )
    res = admin_post(
        client,
        token,
        f"/admin/calendar/{entry_id}/delete",
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Entry deleted" in res.data
    with app.app_context():
        assert calendar_model.get_entry(entry_id) is None


def test_webhook_list_entries(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
        settings_model.set("weather_timezone", "America/Denver")
        from app.helpers import today_local
        from datetime import timedelta

        day = (today_local() + timedelta(days=1)).isoformat()
        calendar_model.create_entry(day, "chore", "alpha")
        calendar_model.create_entry(day, "appointment", "beta")

    res = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"text": "cancel event on tomorrow"},
    )
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert data["action"] == "list_entries"
    assert data["result"]["entry_date"] == day
    assert len(data["result"]["entries"]) == 2


def test_webhook_delete_entry_ids(client, app):
    with app.app_context():
        settings_model.set("webhook_token", "secret-token")
        from app.helpers import today_local

        day = today_local().isoformat()
        id_a = calendar_model.create_entry(day, "chore", "one")
        id_b = calendar_model.create_entry(day, "chore", "two")
        id_c = calendar_model.create_entry(day, "chore", "three")

    res = client.post(
        "/api/webhook",
        headers=_auth_headers("secret-token"),
        json={"intent": "delete", "entry_ids": [id_a, id_c]},
    )
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert data["action"] == "delete_entry"
    assert data["result"]["deleted"] == 2
    with app.app_context():
        assert calendar_model.get_entry(id_a) is None
        assert calendar_model.get_entry(id_b) is not None
        assert calendar_model.get_entry(id_c) is None
