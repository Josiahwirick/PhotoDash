"""Photo metadata CRUD."""

from __future__ import annotations

from sqlite3 import Row

from app.db import get_db


def list_active() -> list[Row]:
    return get_db().execute(
        "SELECT * FROM photos WHERE active = 1 ORDER BY uploaded_at ASC, id ASC"
    ).fetchall()


def list_all() -> list[Row]:
    return get_db().execute(
        "SELECT * FROM photos ORDER BY uploaded_at DESC, id DESC"
    ).fetchall()


def get_photo(photo_id: int) -> Row | None:
    return get_db().execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()


def create_photo(
    *,
    filename: str,
    original_name: str,
    width: int,
    height: int,
    rotated: bool,
    rotation_degrees: int,
    mime_type: str,
) -> int:
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO photos
          (filename, original_name, width, height, rotated, rotation_degrees, mime_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            original_name,
            width,
            height,
            1 if rotated else 0,
            rotation_degrees,
            mime_type,
        ),
    )
    db.commit()
    return int(cur.lastrowid)


def set_active(photo_id: int, active: bool) -> None:
    db = get_db()
    db.execute(
        "UPDATE photos SET active = ? WHERE id = ?",
        (1 if active else 0, photo_id),
    )
    db.commit()


def delete_photo(photo_id: int) -> Row | None:
    db = get_db()
    row = db.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if row is None:
        return None
    db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    db.commit()
    return row
