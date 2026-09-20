"""Admin UI: login + HTMX CRUD."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app import auth
from app.blueprints.webhook import get_webhook_token, regenerate_webhook_token
from app.csrf import validate_csrf
from app.helpers import today_local
from app.models import calendar as calendar_model
from app.models import people as people_model
from app.models import photos as photos_model
from app.models import settings as settings_model
from app.services import photo_pipeline
from app.services.weather_fetcher import fetch_and_cache
from app.validation import (
    normalize_hex_color,
    parse_bounded_int,
    validate_storage_path_setting,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")

ENTRY_TYPES = ("chore", "appointment", "reminder")


@bp.before_request
def protect_admin():
    if request.method == "POST":
        validate_csrf()
    if request.endpoint in ("admin.login", "admin.login_post"):
        return None
    if not auth.is_admin():
        return redirect(url_for("admin.login", next=request.path))
    return None


@bp.get("/login")
def login():
    if auth.is_admin():
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html")


@bp.post("/login")
def login_post():
    password = request.form.get("password", "")
    if auth.verify_password(password):
        auth.login_admin()
        nxt = request.args.get("next") or url_for("admin.dashboard")
        if not nxt.startswith("/admin"):
            nxt = url_for("admin.dashboard")
        return redirect(nxt)
    flash("Incorrect password.", "error")
    return render_template("admin/login.html"), 401


@bp.post("/logout")
def logout():
    auth.logout_admin()
    return redirect(url_for("admin.login"))


@bp.get("/")
def dashboard():
    today = today_local().isoformat()
    return render_template(
        "admin/dashboard.html",
        photo_count=len(photos_model.list_all()),
        people_count=len(people_model.list_people()),
        entry_count=len(calendar_model.list_from_date(today, 1000)),
    )


# --- Photos ---


@bp.get("/photos")
def photos():
    return render_template("admin/photos.html", photos=photos_model.list_all())


@bp.post("/photos/upload")
def photos_upload():
    files = request.files.getlist("photos")
    if not files:
        flash("No files selected.", "error")
        return redirect(url_for("admin.photos"))

    root = photo_pipeline.resolve_storage_path(current_app.config["STORAGE_PATH"])
    saved = 0
    for f in files:
        if not f or not f.filename:
            continue
        try:
            photo_pipeline.process_and_store(f, root)
            saved += 1
        except Exception as exc:  # noqa: BLE001
            flash(f"Failed to process {f.filename}: {exc}", "error")
    if saved:
        flash(f"Uploaded {saved} photo(s).", "ok")
    return redirect(url_for("admin.photos"))


@bp.post("/photos/<int:photo_id>/toggle")
def photos_toggle(photo_id: int):
    photo = photos_model.get_photo(photo_id)
    if photo:
        photos_model.set_active(photo_id, not bool(photo["active"]))
    if request.headers.get("HX-Request"):
        return render_template(
            "admin/partials/photo_row.html", photo=photos_model.get_photo(photo_id)
        )
    return redirect(url_for("admin.photos"))


@bp.post("/photos/<int:photo_id>/delete")
def photos_delete(photo_id: int):
    row = photos_model.delete_photo(photo_id)
    if row:
        photo_pipeline.delete_stored_file(row["filename"], current_app.config["STORAGE_PATH"])
    if request.headers.get("HX-Request"):
        return ""
    flash("Photo deleted.", "ok")
    return redirect(url_for("admin.photos"))


# --- People ---


@bp.get("/people")
def people():
    return render_template("admin/people.html", people=people_model.list_people())


@bp.post("/people")
def people_create():
    name = (request.form.get("name") or "").strip()
    color_raw = request.form.get("color")
    color = normalize_hex_color(color_raw)
    if color_raw and color_raw.strip() and color is None:
        flash("Color must be a valid #RRGGBB value.", "error")
        return redirect(url_for("admin.people"))
    if not name:
        flash("Name is required.", "error")
    else:
        try:
            people_model.create_person(name, color=color)
            flash("Person added.", "ok")
        except Exception as exc:  # noqa: BLE001
            flash(f"Could not add person: {exc}", "error")
    return redirect(url_for("admin.people"))


@bp.post("/people/<int:person_id>")
def people_update(person_id: int):
    name = (request.form.get("name") or "").strip()
    color_raw = request.form.get("color")
    color = normalize_hex_color(color_raw)
    if color_raw and color_raw.strip() and color is None:
        flash("Color must be a valid #RRGGBB value.", "error")
        return redirect(url_for("admin.people"))
    sort_order = parse_bounded_int(
        request.form.get("sort_order"),
        default=0,
        minimum=-9999,
        maximum=9999,
    )
    if name:
        people_model.update_person(person_id, name=name, color=color, sort_order=sort_order)
        flash("Person updated.", "ok")
    return redirect(url_for("admin.people"))


@bp.post("/people/<int:person_id>/delete")
def people_delete(person_id: int):
    people_model.delete_person(person_id)
    flash("Person deleted.", "ok")
    return redirect(url_for("admin.people"))


# --- Calendar ---


@bp.get("/calendar")
def calendar():
    today = today_local().isoformat()
    return render_template(
        "admin/calendar.html",
        entries=calendar_model.list_from_date(today, 200),
        people=people_model.list_people(),
        entry_types=ENTRY_TYPES,
    )


@bp.post("/calendar")
def calendar_create():
    entry_date = request.form.get("entry_date") or ""
    entry_type = request.form.get("entry_type") or "chore"
    text = (request.form.get("text") or "").strip()
    person_raw = request.form.get("person_id") or ""
    person_id = int(person_raw) if person_raw.isdigit() else None
    if entry_type not in ENTRY_TYPES:
        entry_type = "chore"
    if not entry_date or not text:
        flash("Date and text are required.", "error")
    else:
        calendar_model.create_entry(entry_date, entry_type, text, person_id=person_id)
        flash("Entry added.", "ok")
    return redirect(url_for("admin.calendar"))


@bp.post("/calendar/<int:entry_id>")
def calendar_update(entry_id: int):
    entry_date = request.form.get("entry_date") or ""
    entry_type = request.form.get("entry_type") or "chore"
    text = (request.form.get("text") or "").strip()
    person_raw = request.form.get("person_id") or ""
    person_id = int(person_raw) if person_raw.isdigit() else None
    sort_order = parse_bounded_int(
        request.form.get("sort_order"),
        default=0,
        minimum=-9999,
        maximum=9999,
    )
    if entry_type not in ENTRY_TYPES:
        entry_type = "chore"
    if entry_date and text:
        calendar_model.update_entry(
            entry_id,
            entry_date=entry_date,
            entry_type=entry_type,
            text=text,
            person_id=person_id,
            sort_order=sort_order,
        )
        flash("Entry updated.", "ok")
    return redirect(url_for("admin.calendar"))


@bp.post("/calendar/<int:entry_id>/delete")
def calendar_delete(entry_id: int):
    calendar_model.delete_entry(entry_id)
    flash("Entry deleted.", "ok")
    return redirect(url_for("admin.calendar"))


# --- Settings ---


@bp.get("/settings")
def settings():
    all_settings = settings_model.get_all()
    token = get_webhook_token()
    masked = ""
    if token:
        masked = token[:4] + "…" + token[-4:] if len(token) > 8 else "••••"
    return render_template(
        "admin/settings.html",
        settings=all_settings,
        webhook_token_masked=masked,
        webhook_token_full=token,
        webhook_token_configured=bool(token),
    )


@bp.post("/settings/webhook-token/regenerate")
def settings_regenerate_webhook_token():
    regenerate_webhook_token()
    flash("Webhook token regenerated. Update Discord / automations with the new token.", "ok")
    return redirect(url_for("admin.settings"))


@bp.post("/settings")
def settings_save():
    photo_interval = parse_bounded_int(
        request.form.get("photo_interval_seconds"),
        default=30,
        minimum=5,
        maximum=600,
    )
    frame_poll = parse_bounded_int(
        request.form.get("frame_poll_seconds"),
        default=60,
        minimum=10,
        maximum=600,
    )

    storage_raw = request.form.get("storage_path", "").strip()
    storage_path, storage_err = validate_storage_path_setting(
        storage_raw,
        current_app.config["STORAGE_PATH"],
    )
    if storage_err:
        flash(storage_err, "error")
        return redirect(url_for("admin.settings"))

    updates = {
        "photo_interval_seconds": str(photo_interval),
        "frame_poll_seconds": str(frame_poll),
        "storage_path": storage_path,
    }
    for key in (
        "weather_latitude",
        "weather_longitude",
        "weather_timezone",
    ):
        if key in request.form:
            updates[key] = request.form.get(key, "").strip()

    unit = (request.form.get("temperature_unit") or "F").upper()
    if unit not in ("C", "F"):
        unit = "F"
    updates["temperature_unit"] = unit
    settings_model.set_many(updates)

    new_password = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""
    if new_password:
        if new_password != confirm:
            flash("Password confirmation did not match.", "error")
            return redirect(url_for("admin.settings"))
        auth.set_password(new_password)
        flash("Password updated.", "ok")

    flash("Settings saved.", "ok")

    if request.form.get("refresh_weather"):
        ok = fetch_and_cache()
        flash("Weather refreshed." if ok else "Weather refresh failed (check lat/lon).", "ok" if ok else "error")

    return redirect(url_for("admin.settings"))
