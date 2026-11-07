#!/usr/bin/env python3
"""The live paper fleet — runs the deployed bots from the DB (pf_bots), all in
one process sharing one candle fetch per cycle.

Each bot is an independent paper account (own $10,000 equity, positions,
kill-switch, trade log), keyed by bot id. A cycle resolves each bot's universe
and runs its spec's entries/exits through the same core engine the backtester
uses (via spec_runtime) — the test and the live trade share a code path.
Owner actions (close / adjust stop / adjust TP) are drained from the DB
(pf_position_actions) each cycle.

Usage: python3 -m runtime.fleet.runner          # poll loop (15m cadence)
       python3 -m runtime.fleet.runner --once   # one cycle, then exit
Files: paper/fleet/<bot_id>.json, paper/fleet/fleet.log
"""
import csv
import fcntl
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import core.env  # noqa: F401 — loads .env
from core import regime
from core.strategy import parse as parse_spec
from core.timeframes import DEFAULT_TIMEFRAME, interval_ms
from ..trade_model import klines, M15, TAKER, SLIP, RISK, NOTIONAL_CAP, \
    MAX_CONC, KILL_DD, KILL_LOOKBACK, KILL_PAUSE, START_EQUITY, API

# Live-fleet operational config (benchmark, dashboard port, staleness, ntfy
# alert toggles). The bots themselves come from the DB (pf_bots), resolved
# per cycle in cycle_db — there is no static strategy config.

# Regime dial retired — books trade at all times. regime.py stays for ema_bull
# (the capit family's btc_bear entry condition) and these aliases, used here and
# by lab/research/seed_pump_events.py.
GATE_WINDOW = regime.WINDOW_MS
GATE_MIN_EV = regime.MIN_EV
GATE_FWD = regime.FWD_BARS_15M            # 24h in 15m bars
GATE_COOLDOWN = regime.COOLDOWN_MS
GATE_LONG_THR = regime.LONG_THR
MOMO_VOL = 2.5
MOMO_HOLD = 48           # 12h
# Hand-entered ("manual" account) trades have no time-based exit; this large
# bar count pushes their computed exits_at ~a year out so the UI reads "open".
MANUAL_HOLD = 35040      # 1y of 15m bars

# Bounded concerns live in the fleet package; re-exported here so the server
# (runtime.server.app) and `import runtime.fleet.runner as pf` callers resolve them.
from .base import DIR, LOG, PAUSE, log, iso
from .state import spath, tpath, load_state, save_state, record_trade
from .alerts import NTFY_CFG, ntfy_topic, notify
from .events import (EVENTS, NOTES, _bot_map, _bot_iv, _mark_t,
                           _load_bot_map, _post_event, emit_events, flush_notes)

_pause_state = [None]
_btc_cache = [0.0, None]        # (ts, is_bear) — 10-min cache for btc_bear()
_fleet_due = {}                 # fleet_id -> epoch sec it's next allowed to run


def _due_bots(bots):
    """Honor each fleet's check_interval_min. A fleet slower than the 15-min loop
    only runs its bots once its interval has elapsed; the default (<=15m) runs
    every cycle. In-memory next-due map — it resets on restart, which just means
    every fleet runs on the first cycle after a restart (harmless)."""
    now = time.time()
    decided = {}
    for b in bots:
        fid = b.get("fleet_id")
        if fid in decided:
            continue
        iv = max(1, int(b.get("check_interval_min") or 15))
        decided[fid] = iv <= 15 or now >= _fleet_due.get(fid, 0.0)
        if decided[fid] and iv > 15 and fid is not None:
            _fleet_due[fid] = now + iv * 60 - 30
    out = [b for b in bots if decided.get(b.get("fleet_id"), True)]
    if len(out) != len(bots):
        log(f"cadence: {len(bots) - len(out)} bot(s) not due this cycle")
    return out


def btc_bear():
    """True when BTC 4h EMA20 <= EMA50 (bear), matching btc_regime() in
    long_robustness.py (bull is strictly EMA20 > EMA50 on the last CLOSED
    4h candle). None on fetch failure — treated as gate closed. 10m cache."""
    if time.time() - _btc_cache[0] < 600 and _btc_cache[1] is not None:
        return _btc_cache[1]
    url = f"{API}?symbol=BTCUSDT&interval=4h&limit=200"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            rows = json.loads(r.read())
        now = int(time.time() * 1000)
        closes = [float(x[4]) for x in rows if int(x[6]) <= now]
        if len(closes) < 60:
            return _btc_cache[1]
        _btc_cache[0], _btc_cache[1] = time.time(), not regime.ema_bull(closes)
        return _btc_cache[1]
    except Exception:
        return _btc_cache[1]


def _resolve_universes(bots):
    """{bot_id: {ticker: binance_symbol}} resolved per bot from pf_universes
    (the only source). A bot whose spec names no universe, or an unresolvable
    slug, maps to {} and won't open new positions; no founder-universe fallback.
    Slugs are cached, so N bots sharing a universe cost one DB read."""
    from core import db as coredb
    cache = {}
    out = {}
    for b in bots:
        slug = (b.get("spec") or {}).get("universe")
        if slug and slug not in cache:
            cache[slug] = coredb.universe_symbols(slug) or {}
        uni = cache.get(slug, {})
        if not uni:
            log(f"[{b['name']}] universe {slug!r} did not resolve from the DB")
        out[b["id"]] = uni
    return out


def _bot_timeframe(spec):
    try:
        return parse_spec(spec).get("_timeframe", DEFAULT_TIMEFRAME)
    except Exception:
        return None


def _bot_bars(spec):
    """Bars a live cycle must fetch to cover the strategy's lookback and hold."""
    try:
        s = parse_spec(spec)
    except Exception:
        return 110
    hold = int((s.get("exit") or {}).get("time_bars", 16))
    return min(1500, max(110, s["_lookback"] + 2, hold + 8))


def cycle_db(states):
    """One live cycle over the DB fleet. Replaces the fleet_config/VARIANTS
    dispatch: load bots from pf_bots, resolve each bot's own universe, fetch
    candles for each candle size, and run exits+entries for each through
    spec_runtime (which calls the same core functions the backtester uses).
    State is one paper account per bot id."""
    from . import source
    from .. import spec_runtime

    bots = source.load_fleet()
    if not bots:
        log("no runnable bots in pf_bots — idle cycle")
        return
    bots = _due_bots(bots)
    if not bots:
        return  # every fleet's cadence says wait — nothing to do this cycle
    universes = _resolve_universes(bots)
    by_interval = {}
    bars_by_interval = {}
    for b in bots:
        iv = _bot_timeframe(b.get("spec") or {})
        if not iv:
            log(f"[{b['name']}] SKIP: spec has an unsupported candle size")
            continue
        by_interval.setdefault(iv, {})
        _bot_iv[b["id"]] = interval_ms(iv)
        bars_by_interval[iv] = max(bars_by_interval.get(iv, 0),
                                   _bot_bars(b.get("spec") or {}))
        by_interval[iv].update(universes.get(b["id"]) or {})
    if not any(by_interval.values()):
        log("no bot universe resolved — nothing to fetch this cycle")
        return
    # Weather uses BTC's 15m tape regardless of the bot's execution candle.
    by_interval.setdefault(DEFAULT_TIMEFRAME, {})["BTC"] = "BTCUSDT"
    candles_by_interval = {}
    for iv, symbols in by_interval.items():
        if not symbols:
            continue
        limit = bars_by_interval.get(iv, 110)
        with ThreadPoolExecutor(max_workers=6) as ex:
            candles = dict(zip(symbols, ex.map(
                lambda tk: klines(symbols[tk], limit=limit, interval=iv),
                symbols)))
        n_ok = sum(1 for c in candles.values() if c)
        if n_ok < len(symbols) * 0.8:
            log(f"WARN: only {n_ok}/{len(symbols)} {iv} tickers fetched; "
                "skipping that candle size this cycle")
            continue
        candles_by_interval[iv] = candles
    if not candles_by_interval:
        log("no candle size fetched — skipping cycle")
        return
    gate = dict(bear=btc_bear())
    paused = os.path.exists(PAUSE)
    if paused != _pause_state[0]:
        if _pause_state[0] is not None or paused:
            log("trading PAUSED — no new entries; open positions still managed"
                if paused else "trading RESUMED")
        _pause_state[0] = paused

    for b in bots:
        if b["id"] not in states:
            st = load_state(b["id"])
            if not st.get("eq_hist") and not st.get("trades") and not st.get("positions"):
                legacy = load_state(b["name"])
                if legacy.get("eq_hist") or legacy.get("trades") or legacy.get("positions") or legacy.get("equity", START_EQUITY) != START_EQUITY:
                    st = legacy
            states[b["id"]] = st
        # Refresh the per-fleet kill-switch each cycle so editing it in Settings
        # takes effect live; spec_runtime reads st["kill_dd"] (fraction).
        kp = b.get("kill_pct")
        states[b["id"]]["kill_dd"] = (kp / 100.0) if isinstance(kp, (int, float)) else KILL_DD
    prev_counts = {b["id"]: len(states[b["id"]].get("trades", []))
                   for b in bots}
    fetch = lambda sym, start, limit, iv: klines(
        sym, limit=limit, start=start, interval=iv)
    # paused -> no entry scan (empty candle set), but exits still resolve
    spec_runtime.run_fleet(
        bots, states, {} if paused else candles_by_interval, universes,
        fetch=fetch, gate=gate, notes=NOTES, log=log)
    # latest price per ticker from this cycle's candles, for marking open
    # positions to market (so the equity mark moves intraday, not only on close)
    px_now = {}
    for _cand in candles_by_interval.values():
        for _tk, _cs in _cand.items():
            if _cs:
                px_now[_tk] = _cs[-1]["c"]

    def _mtm_equity(st):
        """Realized equity + unrealized P&L of open positions at the latest
        price. This is the account's true equity right now, so the curve drawn
        from marks wiggles with open positions instead of stepping only on
        close."""
        eq = st.get("equity", START_EQUITY)
        for p in st.get("positions", []):
            px, entry = px_now.get(p.get("ticker")), p.get("entry")
            if not px or not entry:
                continue
            sign = 1 if p.get("side", 1) in (1, "long") else -1
            eq += p.get("notional", 0.0) * sign * (px / entry - 1)
        return eq

    def _apply_position_actions(bot_id, st):
        """Honor owner actions queued from the web (close / adjust stop / tp).
        A close realizes P&L at the current price exactly like a normal exit
        (same fee model), appends the trade, and removes the position — so it
        flows out through the trade/mark write below like any other close."""
        from .. import pf_db
        try:
            acts = pf_db.get(
                "pf_position_actions",
                f"bot_id=eq.{bot_id}&status=eq.pending&select=id,ticker,action,value")
        except Exception:
            return
        for a in acts:
            try:
                tk = a.get("ticker")
                pos = next((p for p in st.get("positions", []) if p.get("ticker") == tk), None)
                if a["action"] == "close" and pos:
                    px = px_now.get(tk)
                    if not px or not pos.get("entry"):
                        continue  # can't price it yet — leave pending, retry next cycle
                    side = 1 if pos.get("side", 1) in (1, "long") else -1
                    net = side * (px / pos["entry"] - 1) - (2 * TAKER + SLIP)
                    pnl = pos.get("notional", 0.0) * net
                    if pos.get("margin"):
                        pnl = max(pnl, -pos["margin"])
                    now_ms = int(time.time() * 1000)
                    st["equity"] = st.get("equity", START_EQUITY) + pnl
                    st.setdefault("eq_hist", []).append([now_ms, st["equity"]])
                    st["positions"].remove(pos)
                    st.setdefault("trades", []).append({
                        "t_sig": pos.get("t_sig"), "exit_t": now_ms, "ticker": tk,
                        "side": "long" if side == 1 else "short", "kind": "manual",
                        "net": round(net, 6), "pnl": round(pnl, 2),
                        "notional": round(pos.get("notional", 0.0), 2),
                        "entry": pos.get("entry")})
                    log(f"[{bot_id}] MANUAL CLOSE {tk} net {net * 100:+.2f}% pnl {pnl:+.2f}")
                elif a["action"] == "set_stop" and pos and a.get("value") is not None:
                    pos["stop"] = float(a["value"])
                elif a["action"] == "set_tp" and pos and a.get("value") is not None:
                    pos["tp"] = float(a["value"])
                pf_db.patch("pf_position_actions", f"id=eq.{a['id']}", {"status": "done"})
            except Exception:
                try:
                    pf_db.patch("pf_position_actions", f"id=eq.{a['id']}", {"status": "error"})
                except Exception:
                    pass

    for b in bots:
        st = states[b["id"]]
        _apply_position_actions(b["id"], st)
        # A duplicate engine instance that loaded no local state marks a fresh
        # account (equity=START, no trades, no positions) every cycle — that
        # spurious series is what makes the chart sawtooth. Don't write it.
        if (st.get("equity", START_EQUITY) == START_EQUITY
                and not st.get("trades") and not st.get("positions")):
            save_state(b["id"], st)
            continue
        try:
            from .. import pf_db
            for tr in st.get("trades", [])[prev_counts[b["id"]]:]:
                pf_db.save_trade({"bot_id": b["id"], "t_sig": tr.get("t_sig"),
                                  "exit_t": tr.get("exit_t"),
                                  "ticker": tr.get("ticker"),
                                  "side": tr.get("side", b.get("direction") or "long"),
                                  "kind": tr.get("kind"),
                                  "net": tr.get("net"), "pnl": tr.get("pnl"),
                                  "notional": tr.get("notional"),
                                  "entry": tr.get("entry"),
                                  "exit_px": None})
            trs = st.get("trades", [])
            closed_n = max(len(st.get("eq_hist", [])), len(trs))
            win_pct = round(sum(1 for t in trs if float(t.get("pnl", t.get("net", 0)) or 0) > 0) / len(trs) * 100, 1) if trs else None
            mtm = _mtm_equity(st)
            pf_db.save_mark({
                "bot_id": b["id"],
                # snap to the bot's candle grid so the curve sits on clean
                # boundaries; the (bot_id, t) upsert refines this bar each cycle.
                "t": _mark_t(b["id"]),
                "equity": mtm,
                "ret": mtm / START_EQUITY - 1,
                "open_json": st.get("positions", []),
                "closed": closed_n,
                "win": win_pct,
                "kill": bool(st.get("kill_until", 0) > time.time() * 1000),
                "paused": os.path.exists(PAUSE) or b.get("fleet_status") == "paused",
            })
        except Exception:
            pass
        save_state(b["id"], st)
    flush_notes()


def pstr(cfg):
    mode, parm = cfg["stop"]
    if cfg.get("engine") == "books":
        return "PORTFOLIO: " + " | ".join(
            f"{bn}({b['kind']}"
            + (f",{len(b['only'])}tk" if b.get("only") else "")
            + (",gated" if b.get("btc_bear") else "")
            + f",w{b.get('risk_w', 1.0):g})"
            for bn, b in cfg["books"].items())
    if cfg.get("engine") == "churn":
        return (f"fade biggest 1h mover >={cfg.get('min_move', 0.01)*100:g}% "
                f"every {cfg.get('every', 4)*15}m hold={cfg['hold']*15}m "
                "stop=1h-extreme")
    if cfg.get("engine") == "super":
        s_, c_ = cfg["sizing"]["S"], cfg["sizing"]["C"]
        return (f"SUPER: S pump>={cfg['runup']*100:.0f}% hold={cfg['hold']*15//60}h "
                f"{s_[1]:g}x quad-size c{s_[3]*100:.0f} | "
                f"C capit-{cfg['depth']*100:.0f}% hold={cfg.get('c_hold', 192)*15//60}h "
                f"{c_[1]:g}x c{c_[3]*100:.0f} +btc-bear | margin-floored")
    if cfg.get("engine") == "loser":
        exit_s = (f"tp+{cfg['tp']*100:g}%/close" if cfg.get("tp")
                  else "no-stop")
        return (f"long biggest 1h loser <=-{cfg.get('min_move', 0.02)*100:g}% "
                f"every {cfg.get('every', 4)*15}m hold={cfg['hold']*15//60}h "
                f"{exit_s} {cfg.get('slots', 12)}-slot"
                + (f" btc24<={cfg['btc_r24']*100:g}%"
                   if cfg.get("btc_r24") else ""))
    if cfg.get("engine") == "capit":
        stop = "none" if mode == "none" else f"-{parm*100:.0f}% disaster"
        return (f"capit-long drop<=-{cfg['depth']*100:.0f}%/24h "
                f"hold={cfg['hold']*15//60}h stop={stop}"
                + (f" limit-{cfg['limit']*100:.0f}%" if cfg.get("limit") else "")
                + (" +btc-bear" if cfg.get("btc_bear") else " ungated")
                + (f" {len(cfg['only'])}-majors" if cfg.get("only") else ""))
    stop = {"hh": f"hh+{parm*100:.0f}%" if parm else "4h-high",
            "trail": f"trail{parm:g}natr",
            "sig": "signal-level"}[mode]
    return ((f"momo-long " if cfg.get("engine") == "momo" else "")
            + f"runup>={cfg['runup']*100:.0f}% vol>={cfg['vol']:g}x "
            f"hold={cfg['hold']*15//60}h stop={stop}"
            + (f" +veto>{cfg['veto']*100:g}%" if cfg.get("veto") else "")
            + (" two-sided" if cfg.get("twosided") else ""))


def _live_price(symbol):
    try:
        k = klines(symbol, limit=1)
        return k[-1]["c"] if k else None
    except Exception:
        return None


def _push_mark(bot_id, st):
    """Write an immediate mark so a manual close shows up at once (realized
    equity + remaining positions); the next cycle refines it to MTM."""
    from .. import pf_db
    trs = st.get("trades", [])
    closed_n = max(len(st.get("eq_hist", [])), len(trs))
    win_pct = round(sum(1 for t in trs if float(t.get("pnl", t.get("net", 0)) or 0) > 0) / len(trs) * 100, 1) if trs else None
    eq = st.get("equity", START_EQUITY)
    pf_db.save_mark({
        "bot_id": bot_id, "t": _mark_t(bot_id), "equity": eq,
        "ret": eq / START_EQUITY - 1, "open_json": st.get("positions", []),
        "closed": closed_n, "win": win_pct,
        "kill": bool(st.get("kill_until", 0) > time.time() * 1000),
        "paused": os.path.exists(PAUSE)})


def fast_drain(states):
    """Apply queued owner actions within seconds (not on the 15-min cycle). Runs
    in the main loop's wait tick — same thread as the cycle, so no state race."""
    from .. import pf_db
    try:
        acts = pf_db.get("pf_position_actions",
                         "status=eq.pending&select=id,bot_id,ticker,action,value,"
                         "side,notional,stop,tp,symbol"
                         "&order=created_at.asc")
    except Exception:
        return
    for a in acts:
        try:
            bid = a["bot_id"]
            st = states.get(bid)
            if st is None:
                st = load_state(bid)
                states[bid] = st
            tk = a["ticker"]
            pos = next((p for p in st.get("positions", []) if p.get("ticker") == tk), None)
            if a["action"] == "close" and pos:
                px = _live_price(pos.get("symbol") or f"{tk}USDT")
                if px is None:
                    continue  # couldn't price — leave pending, retry next tick
                side = 1 if pos.get("side", 1) in (1, "long") else -1
                net = side * (px / pos["entry"] - 1) - (2 * TAKER + SLIP)
                pnl = pos.get("notional", 0.0) * net
                if pos.get("margin"):
                    pnl = max(pnl, -pos["margin"])
                now_ms = int(time.time() * 1000)
                st["equity"] = st.get("equity", START_EQUITY) + pnl
                st.setdefault("eq_hist", []).append([now_ms, st["equity"]])
                st["positions"].remove(pos)
                tr = {"t_sig": pos.get("t_sig"), "exit_t": now_ms, "ticker": tk,
                      "side": "long" if side == 1 else "short", "kind": "manual",
                      "net": round(net, 6), "pnl": round(pnl, 2),
                      "notional": round(pos.get("notional", 0.0), 2),
                      "entry": pos.get("entry")}
                st.setdefault("trades", []).append(tr)
                save_state(bid, st)
                pf_db.save_trade({"bot_id": bid, **tr, "exit_px": None})
                _push_mark(bid, st)
                log(f"[{bid}] FAST CLOSE {tk} net {net * 100:+.2f}% pnl {pnl:+.2f}")
            elif a["action"] == "set_stop" and pos and a.get("value") is not None:
                pos["stop"] = float(a["value"]); save_state(bid, st)
            elif a["action"] == "set_tp" and pos and a.get("value") is not None:
                pos["tp"] = float(a["value"]); save_state(bid, st)
            elif a["action"] == "open":
                # Hand-entered trade (the "manual" account). Price it live, like a
                # manual close, and append a position the server marks to market.
                if pos is not None:
                    log(f"[{bid}] MANUAL OPEN skipped — {tk} already open")
                else:
                    sym = a.get("symbol") or f"{tk}USDT"
                    px = _live_price(sym)
                    notional = float(a.get("notional") or 0)
                    if px is None or notional <= 0:
                        continue  # couldn't price / no size — leave pending, retry
                    side_i = 1 if str(a.get("side") or 1) in ("1", "long") else -1
                    now_ms = int(time.time() * 1000)
                    st.setdefault("positions", []).append({
                        "ticker": tk, "symbol": sym, "side": side_i, "entry": px,
                        "stop": float(a["stop"]) if a.get("stop") is not None else 0.0,
                        "tp": float(a["tp"]) if a.get("tp") is not None else None,
                        "notional": round(notional, 2), "t_sig": now_ms,
                        "hold": MANUAL_HOLD, "taker": TAKER, "slip": SLIP,
                        "kind": "manual"})
                    save_state(bid, st)
                    _push_mark(bid, st)
                    log(f"[{bid}] MANUAL OPEN {'LONG' if side_i == 1 else 'SHORT'} "
                        f"{tk} @ {px} notional {notional:.2f}")
            pf_db.patch("pf_position_actions", f"id=eq.{a['id']}", {"status": "done"})
        except Exception:
            try:
                pf_db.patch("pf_position_actions", f"id=eq.{a['id']}", {"status": "error"})
            except Exception:
                pass


def main():
    known = {"--once"}
    bad = [a for a in sys.argv[1:] if a not in known]
    if bad:
        # reject unknown flags: a mistyped flag falling through starts a second
        # fleet loop (duplicate trades, tmp-file races)
        sys.exit(f"unknown argument(s): {' '.join(bad)} — valid: "
                 + " ".join(sorted(known)))
    os.makedirs(DIR, exist_ok=True)
    lock = open(os.path.join(DIR, "fleet.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("another fleet instance is already running "
                 "(paper/fleet/fleet.lock is held) — refusing to start")
    lock.write(str(os.getpid()))
    lock.flush()
    # Fleet is the DB (pf_bots): one paper account per bot id, loaded lazily in
    # cycle_db. No fleet_config fingerprint — a bot's spec is its identity.
    states = {}
    log("fleet start | running the DB fleet (pf_bots) through core")
    last_err_note = 0
    while True:
        try:
            cycle_db(states)
        except Exception as e:
            import traceback
            log(f"ERROR cycle: {e!r} | {traceback.format_exc().splitlines()[-3]}")
            if time.time() - last_err_note > 1800:   # max 1 push / 30 min
                last_err_note = time.time()
                notify("Fleet cycle ERROR", repr(e), priority="high",
                       tags="warning", cat="errors")
        if "--once" in sys.argv:
            break
        nxt = (time.time() // 900 + 1) * 900 + 30
        while time.time() < nxt:
            fast_drain(states)   # honor close/adjust within seconds
            time.sleep(min(3, max(nxt - time.time(), 0.1)))


if __name__ == "__main__":
    main()
