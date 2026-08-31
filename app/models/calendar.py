"""Calendar entries CRUD."""

from __future__ import annotations

from sqlite3 import Row

from app.db import get_db


def list_for_dates(dates: list[str]) -> list[Row]:
    if not dates:
        return []
    placeholders = ",".join("?" * len(dates))
    return get_db().execute(
        f"""
        SELECT e.*, p.name AS person_name, p.color AS person_color
        FROM calendar_entries e
        LEFT JOIN people p ON p.id = e.person_id
        WHERE e.entry_date IN ({placeholders})
        ORDER BY e.entry_date ASC, e.sort_order ASC, e.id ASC
        """,
        dates,
    ).fetchall()


def list_upcoming(limit: int = 100) -> list[Row]:
    return get_db().execute(
        """
        SELECT e.*, p.name AS person_name, p.color AS person_color
        FROM calendar_entries e
        LEFT JOIN people p ON p.id = e.person_id
        ORDER BY e.entry_date ASC, e.sort_order ASC, e.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def list_from_date(from_date: str, limit: int = 200) -> list[Row]:
    """Entries on or after from_date (for admin UI)."""
    return get_db().execute(
        """
        SELECT e.*, p.name AS person_name, p.color AS person_color
        FROM calendar_entries e
        LEFT JOIN people p ON p.id = e.person_id
        WHERE e.entry_date >= ?
        ORDER BY e.entry_date ASC, e.sort_order ASC, e.id ASC
        LIMIT ?
        """,
        (from_date, limit),
    ).fetchall()


def get_entry(entry_id: int) -> Row | None:
    return get_db().execute(
        """
        SELECT e.*, p.name AS person_name
        FROM calendar_entries e
        LEFT JOIN people p ON p.id = e.person_id
        WHERE e.id = ?
        """,
        (entry_id,),
    ).fetchone()


def create_entry(
    entry_date: str,
    entry_type: str,
    text: str,
    person_id: int | None = None,
    sort_order: int = 0,
) -> int:
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO calendar_entries (entry_date, person_id, entry_type, text, sort_order)
        VALUES (?, ?, ?, ?, ?)
        """,
        (entry_date, person_id, entry_type, text.strip(), sort_order),
    )
    db.commit()
    return int(cur.lastrowid)


def update_entry(
    entry_id: int,
    *,
    entry_date: str,
    entry_type: str,
    text: str,
    person_id: int | None = None,
    sort_order: int = 0,
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE calendar_entries
        SET entry_date = ?, person_id = ?, entry_type = ?, text = ?, sort_order = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE id = ?
        """,
        (entry_date, person_id, entry_type, text.strip(), sort_order, entry_id),
    )
    db.commit()


def delete_entry(entry_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM calendar_entries WHERE id = ?", (entry_id,))
    db.commit()
