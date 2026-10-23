"""load_fleet() reads the live bots from pf_bots — the source of what trades.
Trusted server read with the service key, so the engine runs every user's bot
of any visibility (RLS is the web app's concern).

A bot is {id, name, owner, spec}; spec is the canonical core Strategy run via
spec_runtime. Bots without a spec, disabled, or not live are skipped.
"""
import json
import os
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def enabled():
    return bool(URL and KEY)


def load_fleet():
    """-> [{id, name, owner, spec}] for enabled, live bots that carry a spec.
    Empty list if the DB is unconfigured or unreachable."""
    if not enabled():
        return []
    q = ("pf_bots?select=id,name,owner,spec,stage,enabled"
         "&enabled=eq.true&stage=eq.live&spec=not.is.null")
    req = urllib.request.Request(
        f"{URL}/rest/v1/{q}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read())
    return [{"id": x["id"], "name": x["name"], "owner": x.get("owner"),
             "spec": x["spec"]}
            for x in rows if x.get("spec")]
