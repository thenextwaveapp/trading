"""Mirror trade events into the product feed (pf_events), best-effort. Threaded
fire-and-forget with the Supabase service key — a feed hiccup never blocks or
breaks a trading cycle. NOTES is the per-cycle buffer the loop appends to;
flush_notes drains it into one phone push + one feed row per event."""
import json
import os
import threading
import time
import urllib.request

from .base import DIR
from .alerts import notify
from ..trade_model import M15

EVENTS = os.path.join(DIR, "pump_events.json")
NOTES = []                                 # per-cycle buffer -> one push/event

PF_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
PF_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_bot_map = [None]                          # name -> {id, visibility, market}
_bot_iv: dict = {}                         # bot_id -> candle interval (ms)


def _mark_t(bot_id):
    """Snap now to the bot's own candle grid, so its equity marks land on clean
    boundaries at the bot's resolution — a 1m scalper keeps 1m marks, a 15m bot
    stays lean. Each bot's curve is its own line, so mixed grids coexist fine."""
    g = _bot_iv.get(bot_id) or M15
    return (int(time.time() * 1000) // g) * g


def _load_bot_map():
    if _bot_map[0] is None:
        m = {}
        if PF_URL and PF_KEY:
            try:
                req = urllib.request.Request(
                    f"{PF_URL}/rest/v1/pf_bots?select=id,name,visibility,market",
                    headers={"apikey": PF_KEY,
                             "Authorization": f"Bearer {PF_KEY}"})
                for b in json.loads(urllib.request.urlopen(req, timeout=10).read()):
                    m[b["name"]] = b
            except Exception:
                pass
        _bot_map[0] = m
    return _bot_map[0]


def _post_event(row):
    try:
        req = urllib.request.Request(
            f"{PF_URL}/rest/v1/pf_events", data=json.dumps(row).encode(),
            method="POST",
            headers={"apikey": PF_KEY, "Authorization": f"Bearer {PF_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "return=minimal"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def emit_events(notes):
    if not (PF_URL and PF_KEY) or not notes:
        return
    bm = _load_bot_map()
    for n in notes:
        b = bm.get(n["v"], {})
        base = dict(bot_id=b.get("id"), bot_name=n["v"],
                    market=b.get("market", "crypto"),
                    visibility=b.get("visibility", "results"))
        if n["kind"] == "enter":
            row = dict(base, type="entered", payload=dict(
                ticker=n["tk"], side="long" if n["side"] == 1 else "short",
                entry=n.get("px")))
        elif n["kind"] == "exit":
            row = dict(base, type="exited", payload=dict(
                ticker=n["tk"], net=n.get("net"), pnl=n.get("pnl")))
        elif n["kind"] == "kill":
            row = dict(base, type="kill_switch", payload={})
        else:
            continue
        threading.Thread(target=_post_event, args=(row,), daemon=True).start()


def flush_notes():
    """Aggregate the cycle's trade events into one push each: a signal fires
    across many bots at once, so collapse to one notification per event."""
    if not NOTES:
        return
    emit_events(NOTES)                     # mirror to the product feed
    enters = {}
    for n in (x for x in NOTES if x["kind"] == "enter"):
        enters.setdefault((n["tk"], n["side"]), []).append(n)
    for (tk, side), ns in enters.items():
        word = "LONG" if side == 1 else "SHORT"
        notify(f"ENTER {word} {tk} @ {ns[0]['px']}",
               f"runup {ns[0]['runup']*100:+.1f}% | {len(ns)} bots: "
               + ", ".join(x["v"] for x in ns),
               priority="high", cat="entries",
               tags="chart_with_upwards_trend" if side == 1
               else "chart_with_downwards_trend")
    exits = {}
    for n in (x for x in NOTES if x["kind"] == "exit"):
        exits.setdefault(n["tk"], []).append(n)
    for tk, ns in exits.items():
        tot = sum(x["pnl"] for x in ns)
        notify(f"EXIT {tk} {'WIN' if tot > 0 else 'LOSS'} ${tot:+,.0f}",
               ", ".join(f"{x['v']} {x['net']*100:+.1f}%" for x in ns),
               priority="high", cat="exits",
               tags="moneybag" if tot > 0 else "small_red_triangle_down")
    for n in (x for x in NOTES if x["kind"] == "kill"):
        notify(f"KILL-SWITCH: {n['v']}",
               "7d drawdown < -5% — bot paused for 3 days",
               priority="urgent", tags="rotating_light", cat="kill_switch")
    NOTES.clear()
