#!/usr/bin/env python3
"""CLI wrapper to migrate the PhotoDash SQLite database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.migrate import migrate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate PhotoDash SQLite database")
    parser.add_argument(
        "--db",
        default=os.environ.get("PHOTODASH_DB_PATH", str(ROOT / "data" / "photodash.db")),
    )
    parser.add_argument("--password", default=None, help="Bootstrap admin password if unset")
    args = parser.parse_args()
    migrate(Path(args.db), bootstrap_password=args.password)
    print(f"Migrated database at {args.db}")


if __name__ == "__main__":
    main()
