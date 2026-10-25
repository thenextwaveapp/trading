"""Runtime access to the product DB (Supabase PostgREST) with the service key.
Server-side and trusted: bypasses RLS (RLS is the web app's concern).
"""
import json
import os
import urllib.error
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


def _open(req):
    """Open a request, surfacing PostgREST's error body instead of a bare
    'HTTP Error 400' — the worker writes it to pf_backtests.cost_note."""
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()
        raise RuntimeError(f"{e.code} {e.reason}: {detail[:500]}") from None


def get(table: str, query: str = ""):
    """GET rows. `query` is a raw PostgREST query string (select=…&foo=eq.x)."""
    req = urllib.request.Request(f"{URL}/rest/v1/{table}?{query}", headers=_headers())
    return json.loads(_open(req))


def insert(table: str, row: dict):
    req = urllib.request.Request(
        f"{URL}/rest/v1/{table}",
        data=json.dumps(row).encode(),
        method="POST",
        headers=_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}))
    _open(req)


def patch(table: str, query: str, changes: dict):
    req = urllib.request.Request(
        f"{URL}/rest/v1/{table}?{query}",
        data=json.dumps(changes).encode(),
        method="PATCH",
        headers=_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}))
    _open(req)
