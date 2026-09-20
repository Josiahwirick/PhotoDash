#!/usr/bin/env python3
"""Bulk-import images from a folder into PhotoDash storage + DB.

Usage (on the Pi, as root or with env already set):
  sudo -u photodash env $(grep -v '^#' /etc/photodash.env | xargs) \\
    /opt/photodash/.venv/bin/python /opt/photodash/scripts/import_folder.py \\
    /home/pi/pictures
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from werkzeug.datastructures import FileStorage

# Allow running from /opt/photodash
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def convert_heic(src: Path, dest_dir: Path) -> Path | None:
    """Convert HEIC to JPEG via heif-convert or magick. Returns JPEG path."""
    out = dest_dir / f"{src.stem}.jpg"
    if out.exists():
        out.unlink()
    for cmd in (
        ["heif-convert", "-q", "90", str(src), str(out)],
        ["magick", str(src), "-quality", "90", str(out)],
    ):
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            if out.exists() and out.stat().st_size > 0:
                return out
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Source folder of images")
    parser.add_argument("--limit", type=int, default=0, help="Max files (0=all)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    folder: Path = args.folder.resolve()
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 1

    os.chdir(ROOT)
    from app import create_app
    from app.services import photo_pipeline

    app = create_app()
    files = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )
    if args.limit:
        files = files[: args.limit]

    ok = skip = fail = 0
    with app.app_context():
        storage = photo_pipeline.resolve_storage_path(app.config["STORAGE_PATH"])
        print(f"Storage: {storage}")
        print(f"Importing {len(files)} files from {folder}")

        with tempfile.TemporaryDirectory(prefix="photodash-import-") as tmp:
            tmp_path = Path(tmp)
            for path in files:
                try:
                    work = path
                    if path.suffix.lower() == ".heic":
                        converted = convert_heic(path, tmp_path)
                        if converted is None:
                            print(f"FAIL {path.name}: HEIC conversion unavailable")
                            fail += 1
                            continue
                        work = converted

                    if args.dry_run:
                        print(f"DRY  {path.name}")
                        ok += 1
                        continue

                    raw = work.read_bytes()
                    storage_file = FileStorage(
                        stream=BytesIO(raw),
                        filename=path.name,
                        content_type="image/jpeg",
                    )
                    photo_id = photo_pipeline.process_and_store(storage_file, storage)
                    print(f"OK   {path.name} -> id={photo_id}")
                    ok += 1
                except Exception as exc:  # noqa: BLE001 — report and continue
                    print(f"FAIL {path.name}: {exc}")
                    fail += 1

    print(f"Done. ok={ok} fail={fail} skip={skip}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
