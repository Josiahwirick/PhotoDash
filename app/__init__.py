"""PhotoDash Flask application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask

from app import db
from app.config import DEFAULT_SETTINGS, load_config
from app.csrf import get_csrf_token
from app.models import settings as settings_model


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.update(load_config())
    if config_overrides:
        app.config.update(config_overrides)
    logging.basicConfig(level=logging.INFO)

    Path(app.config["DB_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    with app.app_context():
        _ensure_migrated(app)
        _ensure_default_settings()
        _ensure_password(app)

    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.frame import bp as frame_bp
    from app.blueprints.media import bp as media_bp

    app.register_blueprint(frame_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(admin_bp)

    @app.template_global()
    def csrf_token() -> str:
        return get_csrf_token()

    if not app.config.get("TESTING"):
        from app.services.scheduler import init_scheduler

        init_scheduler(app)

    return app


def _ensure_migrated(app: Flask) -> None:
    from app.migrate import migrate

    migrate(Path(app.config["DB_PATH"]), bootstrap_password=app.config.get("BOOTSTRAP_PASSWORD"))


def _ensure_default_settings() -> None:
    for key, value in DEFAULT_SETTINGS.items():
        if settings_model.get(key) is None:
            settings_model.set(key, value)


def _ensure_password(app: Flask) -> None:
    if not settings_model.get("admin_password_hash"):
        from app.auth import set_password

        set_password(app.config.get("BOOTSTRAP_PASSWORD") or "photodash")
