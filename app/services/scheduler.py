"""Background APScheduler jobs."""

from __future__ import annotations

import atexit
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

from app.services.weather_fetcher import fetch_and_cache

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _should_start_scheduler() -> bool:
    # Avoid double-start under gunicorn preload / multiple workers.
    # Prefer a single worker; still guard with env flag.
    if os.environ.get("PHOTODASH_DISABLE_SCHEDULER") == "1":
        return False
    # Gunicorn sets this; only run in the worker process.
    return True


def init_scheduler(app: Flask) -> None:
    global _scheduler
    if not _should_start_scheduler():
        return
    if _scheduler is not None:
        return

    minutes = int(app.config.get("WEATHER_INTERVAL_MINUTES", 30))

    scheduler = BackgroundScheduler(daemon=True)

    def job():
        with app.app_context():
            try:
                fetch_and_cache()
            except Exception:
                logger.exception("Weather job failed")

    scheduler.add_job(
        job,
        "interval",
        minutes=minutes,
        id="weather_fetch",
        replace_existing=True,
        max_instances=1,
    )
    # Run once shortly after startup.
    scheduler.add_job(job, "date", id="weather_fetch_startup", replace_existing=True)
    scheduler.start()
    _scheduler = scheduler
    atexit.register(lambda: scheduler.shutdown(wait=False))
    logger.info("Weather scheduler started (every %s min)", minutes)
