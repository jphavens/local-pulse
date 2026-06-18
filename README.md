# Local Pulse — Docker Deployment
## Wayland, MI Morning News Dashboard on Homelab

---

## Files
```
localpulse/
  Dockerfile          ← builds the container image
  docker-compose.yml  ← run config, ports, env vars
  fetch_news.py       ← RSS fetcher + Claude summarizer
  index.html          ← news dashboard UI
  entrypoint.sh       ← starts web server + cron scheduler
  run_fetch.sh        ← fetch + ntfy notification (runs on cron)
  crontab             ← placeholder (overridden at runtime)
  README.md           ← this file
```

---

## Setup on Your Homelab Server

### 1 — Copy files to server
```bash
scp -r localpulse/ user@YOUR-SERVER-IP:~/localpulse
```
Or use CasaOS File Manager to upload the folder.

### 2 — Set your API key
Create a `.env` file in the localpulse folder:
```bash
cd ~/localpulse
echo "ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE" > .env
```

### 3 — Update SERVER_IP in docker-compose.yml
Open `docker-compose.yml` and set `SERVER_IP` to your homelab server's local IP
(not your PC's IP — the server's IP). Find it with:
```bash
hostname -I | awk '{print $1}'
```

### 4 — Build and start
```bash
cd ~/localpulse
docker compose up -d --build
```

### 5 — Test the fetch manually
```bash
docker exec localpulse python fetch_news.py
```

### 6 — Open the dashboard
In your browser (any device on your network):
```
http://YOUR-SERVER-IP:8765
```

---

## Automation
- Fetches automatically every day at **7:00 AM** (cron inside container)
- Sends ntfy notification to your iPhone via topic `Wayland_Pulse_Havens_24`
- ntfy tap-to-open link uses `SERVER_IP` — always correct now

## Change fetch time
Edit `FETCH_CRON` in `docker-compose.yml`, then:
```bash
docker compose up -d
```

## View logs
```bash
docker logs localpulse                         # container stdout
docker exec localpulse cat /app/data/fetch.log # fetch detail log
docker exec localpulse cat /app/data/cron.log  # cron run log
```

## Trigger a manual fetch
```bash
docker exec localpulse /app/run_fetch.sh
```

## Add to CasaOS
In CasaOS → App Store → Custom Install → paste the docker-compose.yml contents.
Or just run `docker compose up -d` from SSH — CasaOS will show it in the dashboard.

---

## ntfy topic
Your existing topic `Wayland_Pulse_Havens_24` is already configured.
The notification click URL now correctly points to your server IP, not localhost.
