"""People CRUD."""

from __future__ import annotations

from sqlite3 import Row

from app.db import get_db


def list_people() -> list[Row]:
    return get_db().execute(
        "SELECT * FROM people ORDER BY sort_order ASC, name ASC"
    ).fetchall()


def get_person(person_id: int) -> Row | None:
    return get_db().execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()


def get_person_by_name(name: str) -> Row | None:
    """Case-insensitive name lookup."""
    return get_db().execute(
        "SELECT * FROM people WHERE name = ? COLLATE NOCASE",
        (name.strip(),),
    ).fetchone()


def create_person(name: str, color: str | None = None, sort_order: int = 0) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO people (name, color, sort_order) VALUES (?, ?, ?)",
        (name.strip(), color or None, sort_order),
    )
    db.commit()
    return int(cur.lastrowid)


def update_person(
    person_id: int,
    *,
    name: str,
    color: str | None = None,
    sort_order: int = 0,
) -> None:
    db = get_db()
    db.execute(
        "UPDATE people SET name = ?, color = ?, sort_order = ? WHERE id = ?",
        (name.strip(), color or None, sort_order, person_id),
    )
    db.commit()


def delete_person(person_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM people WHERE id = ?", (person_id,))
    db.commit()
