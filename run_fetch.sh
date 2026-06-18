#!/bin/sh
cd /app
python fetch_news.py >> /app/data/fetch.log 2>&1
if [ $? -eq 0 ]; then
    curl -s \
        -H "Title: 📰 Local Pulse" \
        -H "Priority: default" \
        -H "Click: http://${SERVER_IP}:8765" \
        -d "Your morning news digest is ready." \
        http://192.168.4.45:8080/${NTFY_TOPIC}
fi
