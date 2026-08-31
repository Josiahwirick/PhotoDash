"""Test helpers."""

from __future__ import annotations

import re

import pytest

from app import create_app


def csrf_token_from_html(html: bytes) -> str:
    match = re.search(rb'name="csrf_token" value="([^"]+)"', html)
    assert match is not None, "csrf_token field not found in HTML"
    return match.group(1).decode()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    storage = tmp_path / "photos"
    storage.mkdir()
    monkeypatch.setenv("PHOTODASH_DB_PATH", str(db_path))
    monkeypatch.setenv("PHOTODASH_STORAGE_PATH", str(storage))
    monkeypatch.setenv("PHOTODASH_PASSWORD", "testpass")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PHOTODASH_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("PHOTODASH_TESTING", "1")

    application = create_app(
        {
            "TESTING": True,
            "DB_PATH": db_path,
            "STORAGE_PATH": storage,
            "FALLBACK_STORAGE_PATH": storage,
            "BOOTSTRAP_PASSWORD": "testpass",
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    """Logged-in admin client with a valid CSRF token."""
    login_page = client.get("/admin/login")
    token = csrf_token_from_html(login_page.data)
    client.post(
        "/admin/login",
        data={"password": "testpass", "csrf_token": token},
        follow_redirects=True,
    )
    return client, token


def admin_post(client, token: str, *args, **kwargs):
    data = dict(kwargs.pop("data", {}) or {})
    data.setdefault("csrf_token", token)
    return client.post(*args, data=data, **kwargs)
