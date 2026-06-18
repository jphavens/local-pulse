FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy app files
COPY fetch_news.py .
COPY index.html .

# Create directory for generated files
RUN mkdir -p /app/data

# Entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
COPY run_fetch.sh .
RUN chmod +x run_fetch.sh

# Install supercronic for reliable cron in containers
ADD https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic

COPY crontab /app/crontab

EXPOSE 8765

ENTRYPOINT ["/app/entrypoint.sh"]
