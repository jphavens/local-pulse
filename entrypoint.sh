#!/bin/sh
set -e

# Symlink data files into app directory so the web server can serve them
# news.json lives in /app/data (persistent volume), served from /app
ln -sf /app/data/news.json /app/news.json 2>/dev/null || true
ln -sf /app/data/fetch.log /app/fetch.log 2>/dev/null || true

echo "[entrypoint] Starting Local Pulse..."
echo "[entrypoint] Cron schedule: ${FETCH_CRON:-0 7 * * *}"
echo "[entrypoint] ntfy topic: ${NTFY_TOPIC:-not set}"

# Update crontab with the configured schedule
echo "${FETCH_CRON:-0 7 * * *} /app/run_fetch.sh >> /app/data/cron.log 2>&1" > /tmp/crontab

# Start supercronic in background
/usr/local/bin/supercronic /tmp/crontab &

# Start Python web server in foreground
exec python -m http.server 8765 --directory /app
