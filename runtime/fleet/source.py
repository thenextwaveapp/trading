"""load_fleet() reads the deployed bots from pf_bots — the source of what trades.
Trusted server read with the service key, so the engine runs every user's bot
of any visibility (RLS is the web app's concern).

A bot is {id, name, owner, fleet_id, spec, condition_filter} plus the operational
settings of its fleet (pf_fleets): fleet_status, kill_pct, check_interval_min,
fleet_name. spec is the canonical core Strategy run via spec_runtime, and
condition_filter is the Weather gate. Bots without a spec or not deployed are
skipped. (budget_per_bot is intentionally not surfaced here yet — honoring it as
starting capital is a coordinated engine+web change, since the dashboard derives
returns from a flat $10k baseline.)
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import core.env  # noqa: F401 — loads .env
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def enabled():
    return bool(URL and KEY)


def _load_fleets():
    """{fleet_id: {name, status, kill_switch_pct, check_interval_min}} for every
    fleet. Best-effort: an empty map just means bots fall back to defaults."""
    try:
        req = urllib.request.Request(
            f"{URL}/rest/v1/pf_fleets?select=id,name,status,kill_switch_pct,"
            "check_interval_min",
            headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return {f["id"]: f for f in json.loads(r.read())}
    except Exception:
        return {}


def load_fleet():
    """-> [{id, name, owner, fleet_id, spec, condition_filter, fleet_status,
    kill_pct, check_interval_min, fleet_name}] for enabled, live bots that carry
    a spec. Empty list if the DB is unconfigured or unreachable."""
    if not enabled():
        return []
    q = ("pf_bots?select=id,name,owner,fleet_id,spec,condition_filter,stage"
         "&stage=eq.deployed&spec=not.is.null")
    req = urllib.request.Request(
        f"{URL}/rest/v1/{q}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read())
    fleets = _load_fleets()
    out = []
    for x in rows:
        if not x.get("spec"):
            continue
        fl = fleets.get(x.get("fleet_id")) or {}
        out.append({
            "id": x["id"], "name": x["name"], "owner": x.get("owner"),
            "fleet_id": x.get("fleet_id"),
            "spec": x["spec"], "condition_filter": x.get("condition_filter"),
            "fleet_status": fl.get("status") or "active",
            "kill_pct": fl.get("kill_switch_pct"),
            "check_interval_min": int(fl.get("check_interval_min") or 15),
            "fleet_name": fl.get("name"),
        })
    return out
