"""Runtime access to the product DB (Supabase PostgREST) with the service key.
Server-side and trusted: bypasses RLS (RLS is the web app's concern).
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.env  # noqa: F401 — loads .env
import urllib.error
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def enabled() -> bool:
    return bool(URL and KEY)


def save_mark(mark: dict) -> None:
    """Upsert a per-bot live mark into pf_bot_marks (service role)."""
    if not enabled():
        return
    import json as _j
    data = _j.dumps(mark).encode()
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_bot_marks",
        data=data, method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json",
                 "Prefer": "return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception:
        pass


def save_trade(trade: dict) -> None:
    if not enabled():
        return
    import json as _j
    data = _j.dumps(trade).encode()
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_bot_trades", data=data, method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception:
        pass


def save_log(line: str) -> None:
    if not enabled():
        return
    import json as _j, time as _t
    data = _j.dumps({"t": int(_t.time() * 1000), "line": line}).encode()
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_fleet_log", data=data, method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception:
        pass


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
