"""Shared-password session authentication for admin UI."""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import settings as settings_model

F = TypeVar("F", bound=Callable)


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str) -> bool:
    stored = settings_model.get("admin_password_hash")
    if not stored:
        return False
    return check_password_hash(stored, password)


def set_password(password: str) -> None:
    settings_model.set("admin_password_hash", hash_password(password))


def login_admin() -> None:
    session["admin_authenticated"] = True
    session.permanent = True


def logout_admin() -> None:
    session.clear()


def is_admin() -> bool:
    return bool(session.get("admin_authenticated"))


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]
