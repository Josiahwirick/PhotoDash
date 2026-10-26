"""Tests for kiosk heartbeat endpoint and helper."""

from __future__ import annotations

from app.services import kiosk_heartbeat


def test_touch_heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "kiosk-heartbeat"
    monkeypatch.setenv("PHOTODASH_KIOSK_HEARTBEAT_PATH", str(path))
    written = kiosk_heartbeat.touch_heartbeat(dom_ok=True)
    assert written == path
    assert path.is_file()
    assert kiosk_heartbeat.heartbeat_status() == "ok"
    age = kiosk_heartbeat.heartbeat_age_seconds()
    assert age is not None
    assert age < 2.0


def test_touch_heartbeat_dom_fail(tmp_path, monkeypatch):
    path = tmp_path / "kiosk-heartbeat"
    monkeypatch.setenv("PHOTODASH_KIOSK_HEARTBEAT_PATH", str(path))
    kiosk_heartbeat.touch_heartbeat(dom_ok=False)
    assert kiosk_heartbeat.heartbeat_status() == "fail"


def test_touch_heartbeat_with_raf(tmp_path, monkeypatch):
    path = tmp_path / "kiosk-heartbeat"
    monkeypatch.setenv("PHOTODASH_KIOSK_HEARTBEAT_PATH", str(path))
    kiosk_heartbeat.touch_heartbeat(dom_ok=True, raf_seq=42, photo_tick=7)
    data = kiosk_heartbeat.read_heartbeat()
    assert data is not None
    assert data["status"] == "ok"
    assert data["raf"] == 42
    assert data["tick"] == 7
    text = path.read_text()
    assert "raf=42" in text
    assert "tick=7" in text


def test_kiosk_heartbeat_localhost(client, tmp_path, monkeypatch):
    path = tmp_path / "hb"
    monkeypatch.setenv("PHOTODASH_KIOSK_HEARTBEAT_PATH", str(path))
    res = client.post(
        "/api/kiosk-heartbeat",
        json={"dom_ok": True, "raf_seq": 99, "photo_tick": 3},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["dom_ok"] is True
    assert data["raf_seq"] == 99
    assert data["photo_tick"] == 3
    assert path.is_file()
    assert "ok" in path.read_text()
    assert "raf=99" in path.read_text()


def test_kiosk_heartbeat_dom_fail(client, tmp_path, monkeypatch):
    path = tmp_path / "hb"
    monkeypatch.setenv("PHOTODASH_KIOSK_HEARTBEAT_PATH", str(path))
    res = client.post(
        "/api/kiosk-heartbeat",
        json={"dom_ok": False},
    )
    assert res.status_code == 200
    assert res.get_json()["dom_ok"] is False
    assert "fail" in path.read_text()


def test_kiosk_heartbeat_rejects_remote(client, tmp_path, monkeypatch):
    path = tmp_path / "hb"
    monkeypatch.setenv("PHOTODASH_KIOSK_HEARTBEAT_PATH", str(path))
    res = client.post(
        "/api/kiosk-heartbeat",
        json={"dom_ok": True},
        environ_overrides={"REMOTE_ADDR": "192.168.4.50"},
    )
    assert res.status_code == 403
    assert not path.exists()
