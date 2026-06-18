#!/bin/sh
cd /app
python fetch_news.py >> /app/data/fetch.log 2>&1
