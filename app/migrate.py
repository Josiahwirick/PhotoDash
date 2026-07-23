"""Database schema migration and seeding."""

from __future__ import annotations

import os
from pathlib import Path

from werkzeug.security import generate_password_hash

from app.config import DEFAULT_SETTINGS
from app.db import connect

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 1


def migrate(db_path: Path | str, bootstrap_password: str | None = None) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect(db_path)
    try:
        conn.executescript(schema)

        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

        storage = os.environ.get("PHOTODASH_STORAGE_PATH", "")
        if storage:
            existing = conn.execute(
                "SELECT value FROM settings WHERE key = 'storage_path'"
            ).fetchone()
            if existing is None or existing["value"] == "":
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES ('storage_path', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (storage,),
                )

        pw_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'admin_password_hash'"
        ).fetchone()
        if pw_row is None:
            password = bootstrap_password or os.environ.get("PHOTODASH_PASSWORD", "photodash")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ("admin_password_hash", generate_password_hash(password)),
            )

        conn.commit()
    finally:
        conn.close()
