"""Test helpers."""

from __future__ import annotations

import pytest

from app import create_app


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
            "BOOTSTRAP_PASSWORD": "testpass",
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()
