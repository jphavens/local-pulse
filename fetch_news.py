"""
Local Pulse - fetch_news.py
Pulls RSS feeds for Wayland/GR/West MI/Michigan,
sends to Claude API for summarization, saves news.json,
then emails the digest to EMAIL_TO.
"""

import json
import os
import smtplib
import ssl
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

API_KEY        = os.environ.get("ANTHROPIC_API_KEY", "")
EMAIL_FROM     = os.environ.get("EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_TO       = os.environ.get("EMAIL_TO", "havens.jeremy@gmail.com")

# Output goes to /app/data if it exists (Docker), otherwise script dir (local)
SCRIPT_DIR = Path(__file__).parent
DATA_DIR   = Path("/app/data") if Path("/app/data").exists() else SCRIPT_DIR
OUTPUT_FILE = DATA_DIR / "news.json"
LOG_FILE    = DATA_DIR / "fetch.log"

# ── RSS FEEDS ─────────────────────────────────────────────────────────────────
FEEDS = [
    # ── WAYLAND / ALLEGAN / BARRY LOCAL ──────────────────────────────────────
    ("Allegan County News",   "https://news.google.com/rss/search?q=allegan+county+news+michigan&hl=en-US&gl=US&ceid=US:en", "wayland"),
    ("Wayland MI News",       "https://news.google.com/rss/search?q=wayland+michigan&hl=en-US&gl=US&ceid=US:en",             "wayland"),
    ("Hastings Banner",       "https://hastingsbanner.com/feed/",                      "wayland"),
    ("MLive Allegan",         "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=allegan-county",  "wayland"),
    ("MLive Barry County",    "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=barry-county",   "wayland"),
    ("MLive Wayland",         "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=wayland",        "wayland"),

    # ── GRAND RAPIDS ──────────────────────────────────────────────────────────
    ("MLive Grand Rapids",    "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=grand-rapids",   "grand_rapids"),
    ("WOOD TV8",              "https://www.woodtv.com/feed/",                          "grand_rapids"),
    ("WXMI Fox17",            "https://fox17online.com/feed/",                         "grand_rapids"),
    ("Fox17 Local",           "https://fox17online.com/news/feed/",                    "grand_rapids"),
    ("WZZM13",                "https://rssfeeds.wzzm13.com/wzzm13-news",              "grand_rapids"),
    ("Crain's Grand Rapids",  "https://crainsgrandrapids.com/feed/",                   "grand_rapids"),

    # ── WEST MICHIGAN ─────────────────────────────────────────────────────────
    ("MLive West Michigan",   "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=west-michigan",  "west_mi"),
    ("MLive Muskegon",        "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=muskegon",       "west_mi"),
    ("MLive Holland",         "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=holland",        "west_mi"),
    ("MLive Kalamazoo",       "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=kalamazoo",      "west_mi"),

    # ── MICHIGAN STATEWIDE ────────────────────────────────────────────────────
    ("Bridge Michigan",       "https://bridgemi.com/rss.xml",                          "michigan"),
    ("Michigan Public",       "https://www.michiganpublic.org/news/feed/",             "michigan"),
    ("MLive Michigan",        "https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml&tags=michigan", "michigan"),
    ("WLNS Lansing",          "https://www.wlns.com/news/michigan/feed/",              "michigan"),
    ("The Gander Michigan",   "https://gandernewsroom.com/category/michigan/feed/",    "michigan"),
]

MAX_ITEMS_PER_FEED = 5

MAX_STORIES = {
    "wayland":      4,
    "grand_rapids": 4,
    "west_mi":      3,
    "michigan":     3,
}

# ── LOGGING ───────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ── RSS PARSING ───────────────────────────────────────────────────────────────

def fetch_feed(name, url, section, timeout=10):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        import re as _re

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()

        def _clean_and_parse(data):
            text = data.decode("utf-8", errors="ignore")
            text = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
            return ET.fromstring(text.encode("utf-8"))

        def _strip_decl_and_parse(data):
            text = data.decode("utf-8", errors="ignore")
            text = _re.sub(r'<\?xml[^?]*\?>', '', text, count=1).strip()
            text = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
            return ET.fromstring(text.encode("utf-8"))

        root = None
        for attempt in [
            lambda: ET.fromstring(raw),
            lambda: _clean_and_parse(raw),
            lambda: _strip_decl_and_parse(raw),
        ]:
            try:
                root = attempt()
                break
            except ET.ParseError:
                continue

        if root is None:
            log(f"  ✗ {name}: XML parse error (all strategies failed) — skipping")
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        results = []
        for item in items[:MAX_ITEMS_PER_FEED]:
            def txt(tag, ns_prefix=None):
                el = item.find(tag) if not ns_prefix else item.find(f"{ns_prefix}:{tag}", ns)
                return (el.text or "").strip() if el is not None and el.text else ""

            title       = txt("title")
            link        = txt("link") or txt("atom:link", "atom")
            description = txt("description") or txt("summary") or txt("content")
            pub_date    = txt("pubDate") or txt("published") or txt("updated")

            if not link:
                link_el = item.find("atom:link", ns)
                if link_el is not None:
                    link = link_el.get("href", "")

            if title:
                results.append({
                    "source": name,
                    "section": section,
                    "title": title,
                    "link": link,
                    "description": description[:500] if description else "",
                    "pub_date": pub_date,
                })

        log(f"  ✓ {name}: {len(results)} items")
        return results

    except urllib.error.HTTPError as e:
        log(f"  ✗ {name}: HTTP {e.code} — skipping")
        return []
    except urllib.error.URLError as e:
        log(f"  ✗ {name}: URL error {e.reason} — skipping")
        return []
    except ET.ParseError as e:
        log(f"  ✗ {name}: XML parse error — skipping")
        return []
    except Exception as e:
        log(f"  ✗ {name}: {type(e).__name__}: {e} — skipping")
        return []


def fetch_all_feeds():
    log("Fetching RSS feeds...")
    grouped = {k: [] for k in MAX_STORIES}

    for name, url, section in FEEDS:
        items = fetch_feed(name, url, section)
        grouped[section].extend(items)
        time.sleep(0.3)

    for section, items in grouped.items():
        log(f"  Section '{section}': {len(items)} total items before summarization")

    return grouped

# ── CLAUDE SUMMARIZATION ──────────────────────────────────────────────────────

def build_prompt(grouped):
    today = datetime.now().strftime("%A, %B %d, %Y")
    sections_text = ""

    section_labels = {
        "wayland":      "WAYLAND / ALLEGAN COUNTY / BARRY COUNTY (most local — prioritize)",
        "grand_rapids": "GRAND RAPIDS",
        "west_mi":      "WEST MICHIGAN (Ottawa, Muskegon, Allegan, Barry, Ionia counties)",
        "michigan":     "MICHIGAN STATEWIDE",
    }

    for key, label in section_labels.items():
        items = grouped.get(key, [])
        if not items:
            sections_text += f"\n\n## {label}\n(no feed items available)\n"
            continue

        sections_text += f"\n\n## {label}\n"
        for i, item in enumerate(items, 1):
            sections_text += f"\n{i}. [{item['source']}] {item['title']}\n"
            if item['description']:
                sections_text += f"   {item['description'][:300]}\n"
            if item['link']:
                sections_text += f"   URL: {item['link']}\n"
            if item['pub_date']:
                sections_text += f"   Date: {item['pub_date']}\n"

    max_counts = json.dumps(MAX_STORIES)

    return f"""You are a local news summarizer for Jeremy in Wayland, Michigan. Today is {today}.

Below are raw RSS feed items pulled this morning from local news sources. Your job is to:
1. Select the most relevant and newsworthy stories from each section
2. Write a tight 1-2 sentence summary for each
3. Flag upcoming community events with their date/time

Return ONLY a JSON object with no markdown fences, no preamble. Structure:
{{
  "wayland": [ ...stories ],
  "grand_rapids": [ ...stories ],
  "west_mi": [ ...stories ],
  "michigan": [ ...stories ]
}}

Max stories per section: {max_counts}

Each story object:
{{
  "headline": "Concise headline under 15 words",
  "summary": "One to two plain-text sentences under 50 words. No HTML.",
  "source_name": "Publication name",
  "source_url": "The direct article URL — include only if it appears in the feed data",
  "event_date": "ISO 8601 string like 2026-03-05T18:00:00 ONLY if this is an upcoming community event (meeting, festival, public hearing, school event) — null otherwise",
  "event_location": "Venue/address if event, null otherwise"
}}

Rules:
- Prefer hyperlocal stories for the wayland section — Wayland city/township, Wayland Union Schools, Allegan County, Barry County, Hastings, Gun Lake
- Omit duplicate stories (same event covered by multiple sources — pick the best URL)
- Only set event_date for genuine UPCOMING events, not past events or general news
- If a section has no good stories, return []
- Return ONLY valid JSON. No other text whatsoever.

RAW FEED DATA:
{sections_text}"""


def call_claude(prompt):
    if not API_KEY:
        log("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    log("Calling Claude API for summarization...")

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())

        text = ""
        for block in body.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0].strip()

        parsed = json.loads(text)
        log("✓ Claude summarization complete")

        for section, stories in parsed.items():
            log(f"  {section}: {len(stories)} stories")

        return parsed

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        log(f"ERROR: Claude API HTTP {e.code}: {err_body[:300]}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        log(f"ERROR: Could not parse Claude response as JSON: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)


# ── EMAIL ─────────────────────────────────────────────────────────────────────

def format_email_html(news_data):
    today = datetime.now().strftime("%A, %B %d, %Y")

    section_labels = {
        "wayland":      "📍 Wayland / Allegan &amp; Barry County",
        "grand_rapids": "🏙️ Grand Rapids",
        "west_mi":      "🌊 West Michigan",
        "michigan":     "🗺️ Michigan Statewide",
    }

    stories_html = ""
    for key, label in section_labels.items():
        stories = news_data.get(key, [])
        if not stories:
            continue

        stories_html += f"""
        <tr><td style="padding:24px 0 8px;">
          <h2 style="margin:0;font-size:16px;font-weight:700;color:#1a1a2e;
                     border-bottom:2px solid #e8e8f0;padding-bottom:8px;">{label}</h2>
        </td></tr>"""

        for story in stories:
            headline    = story.get("headline", "")
            summary     = story.get("summary", "")
            source_name = story.get("source_name", "")
            source_url  = story.get("source_url", "")
            event_date  = story.get("event_date")
            event_loc   = story.get("event_location")

            event_badge = ""
            if event_date:
                try:
                    dt = datetime.fromisoformat(event_date)
                    event_badge = (
                        f'<span style="display:inline-block;background:#fff3cd;'
                        f'color:#856404;font-size:11px;font-weight:600;'
                        f'padding:2px 8px;border-radius:10px;margin-left:8px;">'
                        f'📅 {dt.strftime("%-m/%-d %-I:%M %p")}'
                        f'{"  📌 " + event_loc if event_loc else ""}</span>'
                    )
                except ValueError:
                    pass

            link_open  = f'<a href="{source_url}" style="color:#1a1a2e;text-decoration:none;">' if source_url else ""
            link_close = "</a>" if source_url else ""
            read_more  = (
                f'  <a href="{source_url}" style="color:#4a6cf7;font-size:12px;'
                f'text-decoration:none;white-space:nowrap;">Read more →</a>'
            ) if source_url else ""

            stories_html += f"""
        <tr><td style="padding:12px 0;border-bottom:1px solid #f0f0f5;">
          <p style="margin:0 0 4px;">
            {link_open}<strong style="font-size:14px;color:#1a1a2e;">{headline}</strong>{link_close}
            {event_badge}
          </p>
          <p style="margin:0 0 4px;font-size:13px;color:#444;line-height:1.5;">
            {summary} {read_more}
          </p>
          <p style="margin:0;font-size:11px;color:#999;">{source_name}</p>
        </td></tr>"""

    fetched_at = news_data.get("fetched_at", "")
    try:
        fetched_dt = datetime.fromisoformat(fetched_at).astimezone().strftime("%-I:%M %p")
    except Exception:
        fetched_dt = fetched_at

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5fa;padding:24px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:12px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- header -->
        <tr><td style="background:linear-gradient(135deg,#1a1a2e,#4a6cf7);
                       padding:28px 32px;">
          <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">
            📰 Local Pulse
          </h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">
            {today} &nbsp;·&nbsp; fetched at {fetched_dt}
          </p>
        </td></tr>

        <!-- stories -->
        <tr><td style="padding:8px 32px 24px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            {stories_html}
          </table>
        </td></tr>

        <!-- footer -->
        <tr><td style="background:#f5f5fa;padding:16px 32px;
                       border-top:1px solid #e8e8f0;">
          <p style="margin:0;font-size:11px;color:#aaa;text-align:center;">
            Local Pulse · Wayland, MI &nbsp;·&nbsp;
            Powered by Claude Haiku
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body></html>"""


def send_email(news_data):
    if not EMAIL_FROM or not EMAIL_PASSWORD:
        log("WARNING: EMAIL_FROM or EMAIL_PASSWORD not set — skipping email")
        return

    today = datetime.now().strftime("%A, %B %d")
    subject = f"📰 Local Pulse — {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    html = format_email_html(news_data)
    msg.attach(MIMEText(html, "html"))

    log(f"Sending digest email to {EMAIL_TO}...")
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        log("✓ Email sent")
    except Exception as e:
        log(f"ERROR sending email: {type(e).__name__}: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("Local Pulse fetch starting")

    grouped = fetch_all_feeds()

    total_items = sum(len(v) for v in grouped.values())
    if total_items == 0:
        log("WARNING: No RSS items retrieved — check internet connection")
        output = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "wayland": [], "grand_rapids": [], "west_mi": [], "michigan": [],
            "error": "No RSS items could be retrieved."
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return

    prompt = build_prompt(grouped)
    news_data = call_claude(prompt)

    news_data["fetched_at"] = datetime.now(timezone.utc).isoformat()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)

    log(f"✓ Saved to {OUTPUT_FILE}")

    send_email(news_data)

    log("Local Pulse fetch complete")
    log("=" * 60)


if __name__ == "__main__":
    main()
