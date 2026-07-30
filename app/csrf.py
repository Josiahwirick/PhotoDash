"""Session CSRF tokens for admin form posts."""

from __future__ import annotations

import secrets
from functools import wraps
from typing import Callable, TypeVar

from flask import abort, request, session

F = TypeVar("F", bound=Callable)


def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf() -> None:
    expected = session.get("csrf_token")
    if not expected:
        abort(400, description="CSRF token missing; reload the page and try again.")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
    if not supplied or not secrets.compare_digest(supplied, expected):
        abort(400, description="CSRF validation failed.")


def csrf_protect(view: F) -> F:
    @wraps(view)
    def wrapped(*args, **kwargs):
        validate_csrf()
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]
