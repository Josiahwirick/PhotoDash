# PhotoDash

Family dashboard / digital photo frame for Raspberry Pi 3 (Raspberry Pi OS Lite, headless).

Full-screen kiosk view: rolling 5-day calendar (yesterday through today+3) + vertical photo strip with crossfade. Configure everything from a shared-password admin UI on your LAN.

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
sudo ./install.sh --with-discord          # optional Discord bot companion
sudo ./install.sh --with-lofi             # optional CLIAMP lofi stream + visualizer strip
sudo ./install.sh --update                # re-sync code, deps, restart services
```

Interactive installs also ask separately whether to enable Discord and/or lofi (default no).

Non-interactive variables: `PHOTODASH_PASSWORD`, `SECRET_KEY`, `PHOTODASH_STORAGE_PATH`, `PHOTODASH_WEATHER_LAT`, `PHOTODASH_WEATHER_LON`, `PHOTODASH_TIMEZONE`, `DISCORD_BOT_TOKEN`, `PHOTODASH_WEBHOOK_TOKEN`, `DISCORD_CHANNEL_ID`, `PHOTODASH_WITH_DISCORD=1`, `PHOTODASH_WITH_LOFI=1`.

After install:

- Frame: `http://<pi-ip>:8080/`
- Admin: `http://<pi-ip>:8080/admin` (or `http://<hostname>.local:8080/admin`)

Point **Settings → storage path** at a USB mount (default `/mnt/usb/photodash/photos`) to reduce SD wear. Set weather lat/lon + timezone so the calendar strip can show conditions.

## Webhook (people & calendar without admin UI)

`POST /api/webhook` accepts structured JSON and/or free-text. Authenticate with:

- `Authorization: Bearer <token>`, or
- `X-PhotoDash-Token: <token>`

The token is shown under **Admin → Settings** (regenerate anytime). Optional env override: `PHOTODASH_WEBHOOK_TOKEN`.

```bash
curl -s -X POST http://127.0.0.1:8080/api/webhook \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"chore tomorrow: take out trash for Estelle"}'
```

Structured example:

```json
{
  "intent": "calendar",
  "entry_type": "appointment",
  "entry_date": "2026-09-20",
  "text": "dentist",
  "person": "Estelle"
}
```

Example phrases: `add person Estelle #7cb89a`, `appointment Friday dentist`, `reminder today pack lunch`, `stop stream`, `start stream`.

## Discord bot

Outbound gateway bot (works behind NAT / Tailscale). Your family can DM the bot instead of using the admin console.

1. Create a Discord application → Bot → enable **Message Content Intent**.
2. Invite the bot (DM + Send Messages).
3. On the Pi:

```bash
sudo DISCORD_BOT_TOKEN=... ./discord_bot/install.sh
```

Or `sudo ./install.sh --with-discord` with `DISCORD_BOT_TOKEN` set (or answer yes when
the installer asks). Config: `/etc/photodash-discord.env`. Logs: `journalctl -u photodash-discord -f`.

Optional `DISCORD_CHANNEL_ID` also accepts messages in one guild channel.

## Lofi strip (CLIAMP)

Optional. Without `--with-lofi` (or answering yes to the installer prompt), the frame
does not reserve space for a visualizer strip.

The strip is fed by [`cliamp visstream`](https://github.com/bjarneo/cliamp) while a
headless CLIAMP daemon plays the built-in lofi stream.

Enable during install:

```bash
sudo ./install.sh --with-lofi
# or later:
sudo ./scripts/install_lofi.sh
```

That installs the arm64/amd64 binary, `photodash-cliamp.service`, and sets
`lofi_installed` / `lofi_enabled` in settings. Turn the strip on/off anytime under
**Admin → Settings** (controls appear only when the feature is installed).

The daemon runs as the kiosk user so it can use PulseAudio/PipeWire. Config/socket
live in `/var/lib/photodash/cliamp` (group `photodash`) so gunicorn can attach
`visstream`. Logs: `journalctl -u photodash-cliamp -f`.

Discord can also send `stop stream` / `start stream` when the bot is installed.

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
| `app/` | Flask app (frame, admin, media, webhook, weather job) |
| `discord_bot/` | Optional Discord gateway companion |
| `deploy/` | systemd units + `xinitrc` |
| `install.sh` | Pi installer |
| `scripts/migrate.py` | DB migrate CLI |

## Services

- `photodash.service` — gunicorn on `:8080`
- `photodash-kiosk.service` — `xinit` → Chromium `--kiosk` (after app)
- `photodash-discord.service` — Discord bot (optional)
- `photodash-cliamp.service` — headless CLIAMP lofi stream (optional)

Screen blanking is disabled in `deploy/xinitrc` via `xset s off -dpms`.

## License

MIT — see [LICENSE](LICENSE).
