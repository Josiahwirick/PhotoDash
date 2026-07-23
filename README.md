# PhotoDash

Family dashboard / digital photo frame for Raspberry Pi 3 (Raspberry Pi OS Lite, headless).

Full-screen kiosk view: rolling 7-day calendar (today centered) + vertical photo strip with crossfade. Configure everything from a shared-password admin UI on your LAN.

## Quick install (on the Pi)

```bash
git clone <this-repo-url> photodash
cd photodash
sudo ./install.sh
```

The installer:

- installs system packages (Python, X11, Chromium, Avahi, …)
- creates the `photodash` service user
- installs the app to `/opt/photodash` with a virtualenv
- writes `/etc/photodash.env`, migrates SQLite, enables systemd units
- starts the app and (unless `--no-kiosk`) the Chromium kiosk

Useful flags:

```bash
sudo ./install.sh --no-kiosk              # app/admin only
sudo ./install.sh --non-interactive       # use env defaults / existing env file
sudo ./install.sh --update                # re-sync code, deps, restart services
```

Non-interactive variables: `PHOTODASH_PASSWORD`, `SECRET_KEY`, `PHOTODASH_STORAGE_PATH`, `PHOTODASH_WEATHER_LAT`, `PHOTODASH_WEATHER_LON`, `PHOTODASH_TIMEZONE`.

After install:

- Frame: `http://<pi-ip>:8080/`
- Admin: `http://<pi-ip>:8080/admin` (or `http://<hostname>.local:8080/admin`)

Point **Settings → storage path** at a USB mount (default `/mnt/usb/photodash/photos`) to reduce SD wear. Set weather lat/lon + timezone so the calendar strip can show conditions.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PHOTODASH_PASSWORD=devpass
export SECRET_KEY=dev
python -c "from app import create_app; create_app().run(debug=True, port=8080)"
```

Or with gunicorn:

```bash
gunicorn --bind 127.0.0.1:8080 --workers 1 --threads 4 "app:create_app()"
```

Tests:

```bash
pip install pytest
pytest -q
```

## Layout

| Path | Role |
|------|------|
| `app/` | Flask app (frame, admin, media, weather job) |
| `deploy/` | systemd units + `xinitrc` |
| `install.sh` | Pi installer |
| `scripts/migrate.py` | DB migrate CLI |

## Services

- `photodash.service` — gunicorn on `:8080`
- `photodash-kiosk.service` — `xinit` → Chromium `--kiosk` (after app)

Screen blanking is disabled in `deploy/xinitrc` via `xset s off -dpms`.

## License

MIT — see [LICENSE](LICENSE).
