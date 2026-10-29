"""Crypto news feed — the engine pulls public RSS and stores headlines.

Raw info only (title, source, link, time), no analysis. Engine writes
pf_news; the web renders it. Keyless RSS so it runs with no credentials; a
per-coin keyed source can be added later without changing the table.

Run:  python3 -m runtime.news_scan            # loop
      python3 -m runtime.news_scan --once     # one pass, exit
"""
import os
import sys
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.env  # noqa: F401
from . import pf_db

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
POLL_SECONDS = 600

FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
]


def _iso(pubdate):
    try:
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def fetch_feed(source, url):
    req = urllib.request.Request(url, headers={"User-Agent": "paperfleet"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    rows = []
    for item in root.iter("item"):
        title = item.findtext("title")
        link = item.findtext("link")
        if not title or not link:
            continue
        rows.append({"url": link.strip(), "title": title.strip(), "source": source,
                     "published_at": _iso(item.findtext("pubDate") or "")})
    return rows


def _upsert(rows):
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_news?on_conflict=url",
        data=json.dumps(rows).encode(), method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


def scan_once():
    rows, seen = [], set()
    for source, url in FEEDS:
        try:
            for row in fetch_feed(source, url):
                if row["url"] in seen:
                    continue
                seen.add(row["url"])
                rows.append(row)
        except Exception as e:
            print(f"news_scan: {source} failed: {e}", file=sys.stderr)
    if rows:
        for i in range(0, len(rows), 200):
            _upsert(rows[i:i + 200])
    return len(rows)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not pf_db.enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    once = "--once" in argv
    while True:
        try:
            print(f"news_scan: upserted {scan_once()} headlines")
        except Exception as e:
            print(f"news_scan error: {e}", file=sys.stderr)
        if once:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
