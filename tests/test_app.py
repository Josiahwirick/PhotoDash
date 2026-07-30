"""Core app and schema tests."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from PIL import Image

from app.helpers import rolling_week_dates, today_local
from app.services.weather_fetcher import map_wmo
from tests.conftest import admin_post


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_frame_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"calendar" in res.data
    assert b"photos" in res.data


def test_admin_requires_login(client):
    res = client.get("/admin/", follow_redirects=False)
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]


def test_admin_login(admin_client):
    client, _token = admin_client
    res = client.get("/admin/")
    assert res.status_code == 200
    assert b"Dashboard" in res.data


def test_rolling_week_centered():
    center = date(2026, 7, 22)  # Wednesday
    days = rolling_week_dates(center)
    assert len(days) == 7
    assert days[3] == center
    assert days[0] == date(2026, 7, 19)
    assert days[6] == date(2026, 7, 25)


def test_wmo_map():
    assert map_wmo(0)[0] == "clear"
    assert map_wmo(61)[0] == "rain"
    assert map_wmo(None)[0] == "unknown"


def test_photo_upload_rotates_landscape(app, admin_client):
    client, token = admin_client

    img = Image.new("RGB", (800, 400), color=(20, 80, 120))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    res = admin_post(
        client,
        token,
        "/admin/photos/upload",
        data={"photos": (buf, "wide.jpg"), "csrf_token": token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        from app.models import photos as photos_model

        rows = photos_model.list_all()
        assert len(rows) == 1
        assert rows[0]["rotated"] == 1
        assert rows[0]["rotation_degrees"] == 90
        assert rows[0]["width"] == 400
        assert rows[0]["height"] == 800


def test_people_and_calendar_crud(app, admin_client):
    client, token = admin_client
    with app.app_context():
        entry_date = today_local().isoformat()
    admin_post(
        client,
        token,
        "/admin/people",
        data={"name": "Alex", "color": "#7cb89a"},
        follow_redirects=True,
    )
    res = client.get("/admin/people")
    assert b"Alex" in res.data

    admin_post(
        client,
        token,
        "/admin/calendar",
        data={
            "entry_date": entry_date,
            "entry_type": "chore",
            "person_id": "1",
            "text": "Take out trash",
        },
        follow_redirects=True,
    )
    cal = client.get("/admin/calendar")
    assert b"Take out trash" in cal.data

    frame = client.get("/api/frame").get_json()
    assert "days" in frame
    assert isinstance(frame["photos"], list)
    assert len(frame["days"]) == 7


def test_admin_post_rejects_missing_csrf(client):
    res = client.post("/admin/login", data={"password": "testpass"})
    assert res.status_code == 400
