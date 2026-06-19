# Local Pulse

Daily local news digest for Wayland, MI. Pulls RSS feeds, summarizes with Claude Haiku, and emails an HTML digest to havens.jeremy@gmail.com every morning at 7am.

## What it does

1. Fetches RSS feeds from ~20 sources across four regions (Wayland/Allegan/Barry, Grand Rapids, West Michigan, Michigan statewide)
2. Sends feed items to Claude Haiku for summarization and story selection
3. Saves the result to `/app/data/news.json`
4. Emails a styled HTML digest via Gmail SMTP

## Files

| File | Purpose |
|------|---------|
| `fetch_news.py` | Main script — RSS fetch, Claude summarization, email send |
| `run_fetch.sh` | Wrapper called by cron — runs fetch_news.py |
| `entrypoint.sh` | Docker entrypoint — sets up symlinks, starts supercronic + web server |
| `docker-compose.yml` | Service definition with env vars and volume |
| `Dockerfile` | Python 3.12-slim image with supercronic |
| `index.html` | Simple web UI served at port 8765 to view news.json |
| `crontab` | Supercronic schedule (overridden by FETCH_CRON env var at runtime) |

## Environment variables

Set in `/home/jeremy/localpulse/.env` on flight-deck (never committed):

```
ANTHROPIC_API_KEY=   # Anthropic API key
EMAIL_FROM=          # Gmail address to send from
EMAIL_PASSWORD=      # Gmail App Password (not your login password)
EMAIL_TO=            # Recipient address (default: havens.jeremy@gmail.com)
TZ=America/Detroit
FETCH_CRON=0 7 * * * # 7am daily
```

`EMAIL_PASSWORD` must be a Gmail App Password generated at myaccount.google.com/apppasswords — not the account login password.

## Running on flight-deck

```sh
ssh jeremy@192.168.4.45
cd /home/jeremy/localpulse

# Rebuild and restart
docker compose down && docker compose up -d --build

# Trigger a manual fetch/email right now
docker exec localpulse python fetch_news.py

# Watch the log
docker exec localpulse tail -f /app/data/fetch.log
```

## Deployed location

- **Host:** flight-deck (`192.168.4.45`)
- **Directory:** `/home/jeremy/localpulse`
- **Container:** `localpulse`
- **Web UI:** `http://192.168.4.45:8765`
- **Schedule:** 7:00 AM America/Detroit daily

## Notifications

Email only (ntfy was removed — it wasn't delivering). Each morning's digest goes to havens.jeremy@gmail.com as a styled HTML email with sections per region and event date badges for upcoming community events.
