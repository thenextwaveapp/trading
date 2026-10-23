"""Runtime access to the product DB (Supabase PostgREST) with the service key.
Server-side and trusted: bypasses RLS (RLS is the web app's concern).
"""
import json
import os
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def enabled() -> bool:
    return bool(URL and KEY)


def _headers(extra=None):
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
    if extra:
        h.update(extra)
    return h


def get(table: str, query: str = ""):
    """GET rows. `query` is a raw PostgREST query string (select=…&foo=eq.x)."""
    req = urllib.request.Request(f"{URL}/rest/v1/{table}?{query}", headers=_headers())
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def insert(table: str, row: dict):
    req = urllib.request.Request(
        f"{URL}/rest/v1/{table}",
        data=json.dumps(row).encode(),
        method="POST",
        headers=_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}))
    urllib.request.urlopen(req, timeout=20)


def patch(table: str, query: str, changes: dict):
    req = urllib.request.Request(
        f"{URL}/rest/v1/{table}?{query}",
        data=json.dumps(changes).encode(),
        method="PATCH",
        headers=_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}))
    urllib.request.urlopen(req, timeout=20)
