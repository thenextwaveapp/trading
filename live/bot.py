#!/usr/bin/env python3
"""LIVE bot — the go-live build. Two books, one Hyperliquid account.

  SHORT book "slow"      : rule P (runup>=12%/4h, first red close, vol>=2x)
                           -> short at close; stop at the 4h high (resting
                           reduce-only stop-market ON EXCHANGE, survives the
                           bot dying); time exit 8h.
  LONG book "capit_slow" : 24h return <= -20% on fresh crossing, BTC 4h
                           EMA20<=EMA50 bear gate -> long at close; NO stop
                           (by spec — stops delete this edge); time exit 48h;
                           sized on 2*NATR24.

  Signals from Binance futures 15m candles — byte-identical logic to the
  paper fleet (live/check_parity.py proves it). Execution on Hyperliquid.

MODES
  dry (default)          : full pipeline, simulated fills at candle closes,
                           HL-level costs. No keys needed. This is the mode
                           the folder ships in — "ready for keys".
  live                   : real orders. Requires ALL THREE:
                             1. live/keys.env   (HL_PRIVATE_KEY, HL_ACCOUNT)
                             2. config.json     "live": true
                             3. live/ARMED      containing the word YES

RISK STACK (all modes)
  0.75% equity risk/trade, 20% notional cap, live hard caps $1000 equity /
  $250 per trade, max 6 concurrent, 1 per coin.
  Kill-switch: 7d -5%  -> no new entries for 3d.
  Daily breaker: 24h -5% -> close everything, halt 24h.
  Weekly breaker: 7d -12% -> close everything, write live/HALTED (manual rm).
  live/PAUSED            -> no new entries, exits still managed (dashboard
                            button). live/FLATTEN -> watcher thread closes
                            every position within ~10s and halts (the
                            emergency button).

Usage: python3 bot.py [--once] [--status]
Files: live/state.json, live/trades.csv, live/bot.log
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

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
CAPS, RISKC, BOOKS, OPS = CFG["caps"], CFG["risk"], CFG["books"], CFG["ops"]
SHORT_BOOK = next(k for k, v in BOOKS.items() if v["side"] == -1)
LONG_BOOK = next(k for k, v in BOOKS.items() if v["side"] == 1)

M15 = 900_000
DAY = 86_400_000
BIN = "https://fapi.binance.com/fapi/v1/klines"
COST = OPS["cost_roundtrip"]
RISK = RISKC["risk_frac"]
NOTIONAL_CAP = RISKC["notional_cap_frac"]
MAX_CONC = RISKC["max_concurrent"]
KILL_DD = RISKC["kill_dd"]
KILL_LOOKBACK = RISKC["kill_lookback_days"] * DAY
KILL_PAUSE = RISKC["kill_pause_days"] * DAY

STATE = os.path.join(HERE, "state.json")
TRADES = os.path.join(HERE, "trades.csv")
LOGF = os.path.join(HERE, "bot.log")
KEYS = os.path.join(HERE, "keys.env")
ARMED = os.path.join(HERE, "ARMED")
HALTED = os.path.join(HERE, "HALTED")
PAUSED = os.path.join(HERE, "PAUSED")
FLATTEN = os.path.join(HERE, "FLATTEN")
NTFY_LOCAL = os.path.join(HERE, "ntfy.json")
NTFY_FLEET = os.path.join(os.path.dirname(HERE), "paper", "fleet", "ntfy.json")

LOCK = threading.Lock()                       # cycle vs flatten watcher


def log(msg):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOGF, "a") as f:
        f.write(line + "\n")


def iso(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%m-%d %H:%M")


def sig5(x):
    """Hyperliquid px rule: <=5 significant figures."""
    return float(f"{x:.5g}")


def ntfy_topic():
    for path in (NTFY_LOCAL, NTFY_FLEET):
        try:
            c = json.load(open(path))
            if c.get("enabled", True) and c.get("topic"):
                return c["topic"]
        except Exception:
            continue
    return None


def notify(title, msg, priority="default", tags=None):
    topic = ntfy_topic()
    if not topic:
        return
    def _send():
        try:
            hdrs = {"Title": title, "Priority": priority}
            if tags:
                hdrs["Tags"] = tags
            req = urllib.request.Request(f"https://ntfy.sh/{topic}",
                                         data=msg.encode(), headers=hdrs)
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


# ---------------------------------------------------------------- data
def klines(symbol, limit=110, start=None):
    url = f"{BIN}?symbol={symbol}&interval=15m&limit={limit}"
    if start is not None:
        url += f"&startTime={start}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                rows = json.loads(r.read())
            now = int(time.time() * 1000)
            return [dict(t=int(x[0]), o=float(x[1]), h=float(x[2]),
                         l=float(x[3]), c=float(x[4]), v=float(x[5]))
                    for x in rows if int(x[6]) <= now]   # closed only
        except Exception as e:
            if attempt == 2:
                log(f"WARN {symbol}: fetch failed ({e})")
                return None
            time.sleep(2 * (attempt + 1))


_btc_cache = [0.0, None]


def btc_bear():
    """True when BTC 4h EMA20 <= EMA50 on the last CLOSED 4h candle.
    None on fetch failure (gate conservatively closed). 10m cache."""
    if time.time() - _btc_cache[0] < 600 and _btc_cache[1] is not None:
        return _btc_cache[1]
    try:
        url = f"{BIN}?symbol=BTCUSDT&interval=4h&limit=200"
        with urllib.request.urlopen(url, timeout=15) as r:
            rows = json.loads(r.read())
        now = int(time.time() * 1000)
        closes = [float(x[4]) for x in rows if int(x[6]) <= now]
        if len(closes) < 60:
            return _btc_cache[1]
        e20 = e50 = closes[0]
        for c in closes:
            e20 += (c - e20) * 2 / 21
            e50 += (c - e50) * 2 / 51
        _btc_cache[0], _btc_cache[1] = time.time(), not (e20 > e50)
        return _btc_cache[1]
    except Exception:
        return _btc_cache[1]


# ------------------------------------------------- pump-event dial (gate30)
# Short book trades only while the trailing 30d mean 24h forward return of
# pump events (any alive bar with runup >= 12%/4h, 24h/ticker cooldown) is
# negative with >= GATE_MIN_EV completed events. Identical machinery to the
# paper fleet's gate30. Store seeds from the fleet's pump_events.json.
GATE_WINDOW = 30 * DAY
GATE_MIN_EV = 10
GATE_FWD = 96
GATE_COOLDOWN = 96 * M15
EVENTS = os.path.join(HERE, "pump_events.json")
EVENTS_FLEET = os.path.join(os.path.dirname(HERE), "paper", "fleet",
                            "pump_events.json")


def load_events():
    if os.path.exists(EVENTS):
        return json.load(open(EVENTS))
    if os.path.exists(EVENTS_FLEET):
        import shutil
        shutil.copy(EVENTS_FLEET, EVENTS)
        log(f"seeded pump-event store from {EVENTS_FLEET}")
        return json.load(open(EVENTS))
    return dict(events=[], last_ev={})


def save_events(store):
    tmp = f"{EVENTS}.tmp.{os.getpid()}"
    json.dump(store, open(tmp, "w"))
    os.replace(tmp, EVENTS)


def detect_events(store, candles):
    for tk, k in candles.items():
        if not k or len(k) < 21:
            continue
        i = len(k) - 1
        if k[i]["t"] - store["last_ev"].get(tk, -10**18) < GATE_COOLDOWN:
            continue
        if k[i]["t"] - k[i - 16]["t"] != 16 * M15:
            continue
        if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
            continue
        if k[i]["c"] / k[i - 16]["c"] - 1 < 0.12:
            continue
        store["events"].append(dict(tk=tk, t=k[i]["t"], px=k[i]["c"],
                                    fwd=None, tries=0))
        store["last_ev"][tk] = k[i]["t"]
        log(f"[dial] pump event {tk} @ {k[i]['c']} "
            f"(+{(k[i]['c'] / k[i - 16]['c'] - 1) * 100:.1f}%/4h)")


def resolve_events(store, uni):
    now = int(time.time() * 1000)
    for ev in store["events"]:
        if ev["fwd"] is not None or ev.get("dead") or ev["tries"] >= 5:
            continue
        done_t = ev["t"] + GATE_FWD * M15
        if now < done_t + 2 * M15 or ev["tk"] not in uni:
            continue
        ev["tries"] += 1
        k = klines(uni[ev["tk"]], limit=2, start=done_t)
        if not k:
            continue
        if k[0]["t"] != done_t:
            ev["dead"] = True
            continue
        ev["fwd"] = k[0]["c"] / ev["px"] - 1
    store["events"] = [e for e in store["events"]
                       if e["t"] >= now - GATE_WINDOW - 5 * DAY]


def dial_state(store):
    now = int(time.time() * 1000)
    done = [e["fwd"] for e in store["events"]
            if e["fwd"] is not None and not e.get("dead")
            and e["t"] >= now - GATE_WINDOW
            and e["t"] + GATE_FWD * M15 <= now]
    n = len(done)
    m = sum(done) / n if n else None
    return dict(short=(n >= GATE_MIN_EV and m < 0), n=n, m=m)


# ---------------------------------------------------------------- signals
# Byte-identical logic to paper_fleet.signal / signal_capit — proven by
# live/check_parity.py. Do not "improve" these.
def signal_short(k, b):
    if len(k) < 21:
        return None
    i = len(k) - 1
    if k[i]["t"] - k[i - 16]["t"] != 16 * M15:
        return None
    if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
        return None
    runup = k[i]["c"] / k[i - 16]["c"] - 1
    if runup < b["runup"] or k[i]["c"] >= k[i - 1]["c"]:
        return None
    mu = sum(x["v"] for x in k[i - 8:i]) / 8
    if mu <= 0 or k[i]["v"] / mu < b["vol"]:
        return None
    hh = max(x["h"] for x in k[i - 16:i + 1])
    return dict(t_sig=k[i]["t"] + M15, entry=k[i]["c"], stop=hh, runup=runup,
                sl_basis=abs(hh / k[i]["c"] - 1))


def signal_capit(k, b):
    if len(k) < 98:
        return None
    i = len(k) - 1

    def cond(j):
        if j < 97:
            return False
        if k[j]["t"] - k[j - 96]["t"] != 96 * M15:
            return False
        if any(x["v"] <= 0 for x in k[j - 8:j + 1]) or k[j]["h"] == k[j]["l"]:
            return False
        return k[j]["c"] / k[j - 96]["c"] - 1 <= -b["depth"]

    if not cond(i) or cond(i - 1):
        return None
    trs = [max(k[j]["h"], k[j - 1]["c"]) - min(k[j]["l"], k[j - 1]["c"])
           for j in range(i - 95, i + 1)]
    natr = (sum(trs) / 96) / k[i]["c"]
    return dict(t_sig=k[i]["t"] + M15, entry=k[i]["c"], stop=0.0,
                runup=k[i]["c"] / k[i - 96]["c"] - 1,
                sl_basis=max(2 * natr, 0.005))


def check_exit_dry(pos, candles):
    """Dry-mode replay: stop breach first (stop 0.0 on a long = unreachable),
    then time exit at the hold-th close. Same semantics as the paper fleet."""
    entry, hold, side = pos["entry"], pos["hold"], pos["side"]
    level = pos["stop"]
    post = [k for k in candles if k["t"] >= pos["t_sig"]][:hold]
    for n, k in enumerate(post, 1):
        if (k["h"] > level) if side < 0 else (k["l"] < level):
            return side * (level / entry - 1) - COST, k["t"] + M15, "sl"
        if n == hold:
            return side * (k["c"] / entry - 1) - COST, k["t"] + M15, "time"
    return None


# ---------------------------------------------------------------- state
def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return dict(equity=CAPS["start_equity_dry"], kill_until=0, halt_until=0,
                last_sig_t=0, positions=[], eq_hist=[])


def save_state(st):
    tmp = f"{STATE}.tmp.{os.getpid()}"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def record_trade(row):
    new = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["coin", "book", "side", "t_sig", "entry", "stop",
                        "exit_t", "kind", "net", "pnl", "notional",
                        "equity_after", "mode"])
        w.writerow(row)


# ---------------------------------------------------------------- hyperliquid
class HL:
    """Thin wrapper; only constructed in live mode."""

    def __init__(self):
        from eth_account import Account
        from hyperliquid.info import Info
        from hyperliquid.exchange import Exchange
        key = os.environ["HL_PRIVATE_KEY"]
        self.addr = os.environ["HL_ACCOUNT"]
        wallet = Account.from_key(key)
        self.info = Info(skip_ws=True)
        self.ex = Exchange(wallet, account_address=self.addr)
        meta = self.info.meta()
        self.szdec = {a["name"]: a["szDecimals"] for a in meta["universe"]
                      if not a.get("isDelisted")}

    def equity(self):
        u = self.info.user_state(self.addr)
        return float(u["marginSummary"]["accountValue"])

    def positions(self):
        u = self.info.user_state(self.addr)
        out = {}
        for ap in u.get("assetPositions", []):
            p = ap["position"]
            szi = float(p["szi"])
            if szi != 0:
                out[p["coin"]] = szi
        return out

    def round_sz(self, coin, sz):
        d = self.szdec.get(coin)
        return round(sz, d) if d is not None else None

    def market_open(self, coin, is_buy, sz):
        return self._fill(self.ex.market_open(coin, is_buy, sz, None, 0.01))

    def market_close(self, coin):
        return self._fill(self.ex.market_close(coin, None, None, 0.01))

    def stop_order(self, coin, is_buy, sz, trigger_px):
        lim = trigger_px * (1.05 if is_buy else 0.95)
        r = self.ex.order(coin, is_buy, sz, sig5(lim),
                          {"trigger": {"triggerPx": sig5(trigger_px),
                                       "isMarket": True, "tpsl": "sl"}},
                          reduce_only=True)
        try:
            s = r["response"]["data"]["statuses"][0]
            return s.get("resting", {}).get("oid")
        except Exception:
            log(f"WARN stop order response: {r}")
            return None

    def cancel_all(self, coin):
        try:
            for o in self.info.open_orders(self.addr):
                if o["coin"] == coin:
                    self.ex.cancel(coin, o["oid"])
        except Exception as e:
            log(f"WARN cancel {coin}: {e!r}")

    def last_fill_px(self, coin):
        try:
            for f in self.info.user_fills(self.addr):
                if f["coin"] == coin:
                    return float(f["px"])
        except Exception:
            pass
        return None

    @staticmethod
    def _fill(r):
        try:
            s = r["response"]["data"]["statuses"][0]
            if "filled" in s:
                return float(s["filled"]["avgPx"]), float(s["filled"]["totalSz"])
            log(f"WARN order not filled: {s}")
        except Exception:
            log(f"WARN order response: {r}")
        return None, None


# ---------------------------------------------------------------- engine
def universe():
    return json.load(open(os.path.join(HERE, "universe.json")))


def mode_str(hl):
    return "LIVE" if hl else "dry"


def book_exit(st, uni, hl, pos, net, exit_t, kind):
    pnl = pos["notional"] * net
    st["equity"] += pnl
    st["eq_hist"].append([exit_t, st["equity"]])
    st["positions"].remove(pos)
    record_trade([pos["coin"], pos["book"], pos["side"], pos["t_sig"],
                  pos["entry"], pos["stop"], exit_t, kind, round(net, 6),
                  round(pnl, 2), round(pos["notional"], 2),
                  round(st["equity"], 2), mode_str(hl)])
    log(f"EXIT [{pos['book']}] {pos['coin']} {kind} net {net*100:+.2f}% "
        f"pnl {pnl:+.2f} equity {st['equity']:.2f}")
    notify(f"{'LIVE ' if hl else ''}EXIT {pos['coin']} "
           f"{'WIN' if pnl > 0 else 'LOSS'} ${pnl:+,.2f}",
           f"[{pos['book']}] {kind} net {net*100:+.2f}% | "
           f"equity {st['equity']:.2f}",
           priority="high" if hl else "default",
           tags="moneybag" if pnl > 0 else "small_red_triangle_down")


def run_exits(st, uni, hl):
    now = int(time.time() * 1000)
    live_pos = hl.positions() if hl else {}
    for pos in list(st["positions"]):
        coin = pos["coin"]
        if hl:
            gone = coin not in live_pos
            expired = now >= pos["t_sig"] + pos["hold"] * M15
            if not gone and not expired:
                continue
            if gone:                       # stop filled on-exchange
                px = hl.last_fill_px(coin) or pos["stop"]
                kind = "sl"
            else:
                hl.cancel_all(coin)
                px, _ = hl.market_close(coin)
                if px is None:
                    log(f"WARN {coin}: time-exit close failed, retry next cycle")
                    continue
                kind = "time"
            hl.cancel_all(coin)
            net = pos["side"] * (px / pos["entry"] - 1) - COST
            book_exit(st, uni, hl, pos, net, now, kind)
        else:
            cnd = klines(uni[coin], limit=min(pos["hold"] + 8, 250),
                         start=pos["t_sig"])
            if cnd is None:
                continue
            ex = check_exit_dry(pos, cnd)
            if ex is None:
                continue
            net, exit_t, kind = ex
            book_exit(st, uni, hl, pos, net, exit_t, kind)


def close_all(st, uni, hl, why):
    for pos in list(st["positions"]):
        if hl:
            hl.cancel_all(pos["coin"])
            px, _ = hl.market_close(pos["coin"])
            if px is None:
                log(f"WARN {pos['coin']}: breaker close failed, will retry")
                continue
            net = pos["side"] * (px / pos["entry"] - 1) - COST
        else:
            k = klines(uni[pos["coin"]], limit=1)
            if not k:
                continue
            net = pos["side"] * (k[-1]["c"] / pos["entry"] - 1) - COST
        book_exit(st, uni, hl, pos, net, int(time.time() * 1000), why)


def breakers(st, now, uni, hl):
    """Returns True when entries are blocked; may close everything."""
    if os.path.exists(HALTED):
        return True
    hist = [e for e in st["eq_hist"] if e[0] >= now - 7 * DAY]
    if hist:
        if st["equity"] / max(e[1] for e in hist) - 1 < RISKC["week_dd"]:
            with open(HALTED, "w") as f:
                f.write(f"7d drawdown breached {RISKC['week_dd']:.0%} at "
                        f"{iso(now)}. Delete this file to re-enable.\n")
            log(f"WEEKLY BREAKER: 7d dd < {RISKC['week_dd']:.0%} — FULL HALT")
            notify("WEEKLY BREAKER — FULL HALT",
                   f"7d drawdown < {RISKC['week_dd']:.0%}; all positions "
                   "closing; rm live/HALTED to resume",
                   priority="urgent", tags="rotating_light")
            close_all(st, uni, hl, "breaker")
            return True
        day = [e for e in hist if e[0] >= now - DAY]
        if day and st["equity"] / max(e[1] for e in day) - 1 < RISKC["day_dd"]:
            if st["halt_until"] < now:
                st["halt_until"] = now + DAY
                log(f"DAILY BREAKER: 24h dd < {RISKC['day_dd']:.0%} — closing "
                    f"all, halt until {iso(st['halt_until'])}")
                notify("DAILY BREAKER", "24h drawdown < -5%; all positions "
                       "closing; 24h entry halt", priority="urgent",
                       tags="rotating_light")
                close_all(st, uni, hl, "breaker")
    return st["halt_until"] > now


def enter(st, uni, hl, coin, book, sig, side):
    stop = sig["stop"]
    b = BOOKS[book]
    size_eq = min(st["equity"], CAPS["equity_cap_usd"]) if hl else st["equity"]
    notional = min(RISK * size_eq / max(sig["sl_basis"], 0.005),
                   NOTIONAL_CAP * size_eq,
                   CAPS["max_notional_usd"] if hl else 1e18)
    # optional signal-strength scaling (size_pow 0 = flat; the Larry dial)
    pow_ = b.get("size_pow", 0.0)
    if pow_:
        ref = b["runup"] if side == -1 else b["depth"]
        notional = min(notional * (abs(sig["runup"]) / ref) ** pow_,
                       NOTIONAL_CAP * size_eq,
                       CAPS["max_notional_usd"] if hl else 1e18)
    # aggregate exposure guard: total open notional never exceeds
    # max_gross_frac of sizing equity — a real account can't commit
    # more than it has (the check Super Larry's sim was missing)
    gross = sum(p["notional"] for p in st["positions"])
    room = RISKC.get("max_gross_frac", 1.0) * size_eq - gross
    if room <= 0:
        log(f"SKIP [{book}] {coin}: gross exposure full "
            f"({gross:.0f}/{size_eq:.0f})")
        return
    if notional > room:
        log(f"[{book}] {coin}: notional trimmed {notional:.0f} -> {room:.0f} "
            "(gross exposure cap)")
        notional = room
    entry_px = sig["entry"]
    if hl:
        sz = hl.round_sz(coin, notional / entry_px)
        if sz is None or sz * entry_px < CAPS["min_order_usd"]:
            log(f"SKIP {coin}: size below HL minimum")
            return
        px, filled = hl.market_open(coin, side == 1, sz)
        if px is None:
            return
        entry_px, notional = px, filled * px
        if side == -1:                     # short book: stop lives on exchange
            oid = hl.stop_order(coin, True, filled, stop)
            if oid is None:
                log(f"WARN {coin}: no resting stop — bot-managed only")
    st["positions"].append(dict(coin=coin, book=book, side=side,
                                t_sig=sig["t_sig"], entry=entry_px, stop=stop,
                                notional=notional, hold=BOOKS[book]["hold"]))
    log(f"ENTER [{book}] {'LONG' if side == 1 else 'SHORT'} {coin} "
        f"@ {entry_px} (move {sig['runup']*100:+.1f}%) stop {stop:.6g} "
        f"notional {notional:.2f} {mode_str(hl)}")
    notify(f"{'LIVE ' if hl else ''}ENTER "
           f"{'LONG' if side == 1 else 'SHORT'} {coin} @ {entry_px}",
           f"[{book}] move {sig['runup']*100:+.1f}% | stop {stop:.6g} | "
           f"notional {notional:.2f}",
           priority="high" if hl else "default",
           tags="chart_with_upwards_trend" if side == 1
           else "chart_with_downwards_trend")


def run_signals(st, uni, candles, bear, dial, hl):
    open_coins = {p["coin"] for p in st["positions"]}
    max_t = st["last_sig_t"]
    for coin, cnd in candles.items():
        if not cnd:
            continue
        found = []
        s = signal_short(cnd, BOOKS[SHORT_BOOK])
        if s:
            gate_ok = dial["short"] if BOOKS[SHORT_BOOK].get("dial_gate") \
                else True
            found.append((SHORT_BOOK, s, -1, gate_ok))
        l = signal_capit(cnd, BOOKS[LONG_BOOK])
        if l:
            gate_ok = (bear is True) if BOOKS[LONG_BOOK]["btc_bear_gate"] \
                else True
            found.append((LONG_BOOK, l, 1, gate_ok))
        for book, sig, side, gate_ok in found:
            max_t = max(max_t, sig["t_sig"])
            if sig["t_sig"] <= st["last_sig_t"]:
                continue
            if not gate_ok:
                if side == -1:
                    m = f"{dial['m']*100:+.2f}%" if dial["m"] is not None \
                        else "n/a"
                    log(f"SKIP [{book}] {coin}: pump dial not negative "
                        f"(n={dial['n']}, m={m})")
                else:
                    log(f"SKIP [{book}] {coin}: BTC bear gate closed"
                        + (" (btc data unavailable)" if bear is None else ""))
                continue
            if coin in open_coins or len(st["positions"]) >= MAX_CONC:
                log(f"SKIP [{book}] {coin}: position/concurrency limit")
                continue
            if sig["t_sig"] < st["kill_until"]:
                log(f"SKIP [{book}] {coin}: kill-switch until "
                    f"{iso(st['kill_until'])}")
                continue
            hist = [e for e in st["eq_hist"]
                    if e[0] >= sig["t_sig"] - KILL_LOOKBACK]
            if hist and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
                st["kill_until"] = sig["t_sig"] + KILL_PAUSE
                log(f"KILL-SWITCH: 7d dd < {KILL_DD:.0%}, pause until "
                    f"{iso(st['kill_until'])}")
                notify("Kill-switch tripped", "7d drawdown < -5% — no new "
                       "entries for 3 days", priority="urgent",
                       tags="rotating_light")
                continue
            enter(st, uni, hl, coin, book, sig, side)
            open_coins.add(coin)
    st["last_sig_t"] = max_t
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= int(time.time() * 1000) - 3 * KILL_LOOKBACK]


_pause_state = [None]


def cycle(st, uni, hl):
    now = int(time.time() * 1000)
    if hl:
        try:
            st["equity"] = hl.equity()
        except Exception as e:
            log(f"WARN equity fetch failed: {e!r} — skipping cycle")
            return
        st["eq_hist"].append([now, st["equity"]])
    with ThreadPoolExecutor(max_workers=6) as ex:
        candles = dict(zip(uni, ex.map(lambda c: klines(uni[c]), uni)))
    ok = sum(1 for c in candles.values() if c)
    if ok < len(uni) * 0.8:
        log(f"WARN only {ok}/{len(uni)} coins fetched, skipping cycle")
        return
    store = load_events()
    detect_events(store, candles)
    resolve_events(store, uni)
    save_events(store)
    dial = dial_state(store)
    bear = btc_bear()
    run_exits(st, uni, hl)
    paused = os.path.exists(PAUSED)
    if paused != _pause_state[0]:
        if _pause_state[0] is not None or paused:
            log("entries PAUSED" if paused else "entries RESUMED")
        _pause_state[0] = paused
    if not breakers(st, now, uni, hl) and not paused:
        run_signals(st, uni, candles, bear, dial, hl)
    save_state(st)


def flatten_watcher(st, uni, hl_ref):
    """Emergency: the dashboard writes live/FLATTEN; within ~10s every
    position is closed at market and the bot halts (live/HALTED)."""
    while True:
        time.sleep(10)
        if not os.path.exists(FLATTEN):
            continue
        with LOCK:
            log("FLATTEN requested — closing every position NOW")
            notify("FLATTEN — closing everything",
                   "manual flatten from the dashboard; bot halting",
                   priority="urgent", tags="rotating_light")
            close_all(st, uni, hl_ref[0], "flatten")
            with open(HALTED, "w") as f:
                f.write(f"flattened manually at "
                        f"{datetime.now(timezone.utc)}. rm to resume.\n")
            os.remove(FLATTEN)
            save_state(st)


def status():
    st = load_state()
    print(f"LIVE BOT  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"mode cfg live={CFG['live']} | armed="
          f"{os.path.exists(ARMED)} | halted={os.path.exists(HALTED)} | "
          f"paused={os.path.exists(PAUSED)}")
    d = dial_state(load_events())
    m = f"{d['m']*100:+.2f}%" if d["m"] is not None else "n/a"
    print(f"equity {st['equity']:.2f} | open {len(st['positions'])} | "
          f"BTC bear: {btc_bear()} | pump dial: "
          f"{'SHORT OPEN' if d['short'] else 'closed'} (n={d['n']}, m={m})")
    for p in st["positions"]:
        print(f"  [{p['book']}] {p['coin']} "
              f"{'long' if p['side'] == 1 else 'short'} @ {p['entry']} "
              f"stop {p['stop']:.6g} since {iso(p['t_sig'])}")


def main():
    if "--status" in sys.argv:
        return status()
    lock = open(os.path.join(HERE, "bot.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("another live bot instance is running — refusing to start")
    lock.write(str(os.getpid()))
    lock.flush()

    # fingerprint the books spec — rule changes must never be silent
    import hashlib
    fp = hashlib.sha256(json.dumps(BOOKS, sort_keys=True).encode()
                        ).hexdigest()[:12]
    fp_path = os.path.join(HERE, "spec_fingerprint.txt")
    old = open(fp_path).read().strip() if os.path.exists(fp_path) else None
    if old and old != fp:
        log(f"SPEC CHANGED: fingerprint {old} -> {fp}")
        notify("LIVE SPEC CHANGED", f"fingerprint {old} → {fp}",
               priority="high", tags="warning")
    with open(fp_path, "w") as f:
        f.write(fp)

    # keys.env -> environment (never committed, chmod 600)
    if os.path.exists(KEYS):
        for ln in open(KEYS):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    hl = None
    if CFG.get("live"):
        armed = os.path.exists(ARMED) and open(ARMED).read().strip() == "YES"
        have_keys = bool(os.environ.get("HL_PRIVATE_KEY")
                         and os.environ.get("HL_ACCOUNT"))
        if armed and have_keys:
            hl = HL()
            log(f"*** LIVE MODE *** account {hl.addr[:8]}… | equity cap "
                f"${CAPS['equity_cap_usd']} | per-trade cap "
                f"${CAPS['max_notional_usd']}")
            # startup reconciliation: the exchange is the truth
            st0 = load_state()
            known = {p["coin"] for p in st0["positions"]}
            on_ex = hl.positions()
            orphans = [c for c in on_ex if c not in known]
            if orphans:
                log(f"WARN ORPHAN positions on exchange not in state: "
                    f"{orphans} — close them manually on the HL UI or add "
                    "to state.json")
                notify("ORPHAN positions on exchange",
                       f"{', '.join(orphans)} — on HL but unknown to the "
                       "bot; review on the HL UI", priority="urgent",
                       tags="warning")
            for p in st0["positions"]:
                if p["coin"] not in on_ex:
                    log(f"note: {p['coin']} in state but not on exchange — "
                        "will book as stop-fill on first cycle")
            notify("LIVE BOT ARMED", f"account {hl.addr[:8]}… | caps "
                   f"${CAPS['equity_cap_usd']}/${CAPS['max_notional_usd']} "
                   f"| books: {SHORT_BOOK} short + {LONG_BOOK} long",
                   priority="high", tags="rocket")
        else:
            missing = [w for w, ok in
                       [("keys.env", have_keys), ("ARMED=YES", armed)] if not ok]
            log(f"live requested but missing: {', '.join(missing)} — "
                "running DRY")
    st = load_state()
    uni = universe()
    log(f"bot start | mode {mode_str(hl)} | books "
        f"{SHORT_BOOK}(short,{BOOKS[SHORT_BOOK]['hold']*15//60}h) + "
        f"{LONG_BOOK}(long,{BOOKS[LONG_BOOK]['hold']*15//60}h,bear-gated) | "
        f"equity {st['equity']:.2f} | open {len(st['positions'])} | "
        f"universe {len(uni)}")
    hl_ref = [hl]
    threading.Thread(target=flatten_watcher, args=(st, uni, hl_ref),
                     daemon=True).start()
    while True:
        try:
            with LOCK:
                cycle(st, uni, hl)
        except Exception as e:
            import traceback
            log(f"ERROR cycle: {e!r} | "
                f"{traceback.format_exc().splitlines()[-3]}")
            notify("Live-bot cycle ERROR", repr(e), priority="high",
                   tags="warning")
        if "--once" in sys.argv:
            break
        now = time.time()
        nxt = (now // 900 + 1) * 900 + 30
        time.sleep(max(nxt - now, 1))


if __name__ == "__main__":
    main()
