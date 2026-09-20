"""Tests for POST /api/webhook."""

from __future__ import annotations

from app.models import calendar as calendar_model
from app.models import people as people_model
from app.models import settings as settings_model


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
