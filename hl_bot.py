#!/usr/bin/env python3
"""Hyperliquid trading bot — the ts30 two-sided regime system from the
research (reports/regime_findings.md):

  signal source : Binance futures 15m candles (identical to every backtest)
  execution     : Hyperliquid perps (58/60 universe tickers listed)
  short book    : runup>=12%/4h, first red close, vol>=2x; stop at 4h high;
                  4h time exit. Open only when regime dial m < 0.
  long book     : runup>=12%/4h, strong close (upper wick<=15%, close in top
                  20% of 4h range), vol>=2.5x; stop at max(4h low, body mid)
                  -0.1%; 12h time exit. Open only when dial m > +2%.
  regime dial   : trailing 30d mean 24h fwd return of completed pump events
                  (>=10 events), maintained live in bot/pump_events.json.
  sizing        : 0.75% equity risk / stop distance, capped at 20% equity
                  and MAX_NOTIONAL_USD. Max 6 concurrent positions.
  kill switches : research 7d -5% -> 3d pause; live extras: 24h -5% -> close
                  all + 24h halt; 7d -12% -> full halt (manual reset).

MODES
  dry (default) : full pipeline, simulated fills at Binance candle closes
                  (same semantics as the paper fleet). No keys needed.
  live          : real orders. Requires ALL of:
                    1. env HL_PRIVATE_KEY  (API-wallet private key)
                    2. env HL_ACCOUNT      (main account address, 0x..)
                    3. --live flag
                    4. file bot/ARMED containing the word YES
                  Sizing equity = min(HL account value, EQUITY_CAP).

Usage: python3 hl_bot.py [--once] [--live] [--short-only] [--status]
Env:   EQUITY_CAP (default 1000 USD), MAX_NOTIONAL_USD (default 250),
       START_EQUITY (dry, default 10000)
Files: bot/state.json, bot/trades.csv, bot/bot.log, bot/pump_events.json
"""
import csv
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import paper_fleet as pf
from paper_fleet import (signal, signal_momo, check_exit, detect_events,
                         resolve_events, gate_state, VARIANTS, MOMO_HOLD,
                         GATE_MIN_EV)
from paper_trader import klines, M15, RISK, NOTIONAL_CAP, MAX_CONC, \
    KILL_DD, KILL_LOOKBACK, KILL_PAUSE

BOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot")
STATE = os.path.join(BOT, "state.json")
TRADES = os.path.join(BOT, "trades.csv")
LOGF = os.path.join(BOT, "bot.log")
EVENTS = os.path.join(BOT, "pump_events.json")
ARMED = os.path.join(BOT, "ARMED")
HALTED = os.path.join(BOT, "HALTED")

CFG = VARIANTS["ts30"]                     # short book params (frozen base)
EQUITY_CAP = float(os.environ.get("EQUITY_CAP", 1000))
MAX_NOTIONAL_USD = float(os.environ.get("MAX_NOTIONAL_USD", 250))
START_EQUITY = float(os.environ.get("START_EQUITY", 10_000))
DAY_DD, DAY_HALT = -0.05, 24 * 3600_000
WEEK_DD = -0.12
MIN_ORDER_USD = 12.0


def log(msg):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOGF, "a") as f:
        f.write(line + "\n")


pf.log = log          # route event-store logging into the bot's log


def iso(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%m-%d %H:%M")


def sig5(x):
    """Hyperliquid px rule: <=5 significant figures."""
    return float(f"{x:.5g}")


# ---------------------------------------------------------------- state
def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return dict(equity=START_EQUITY, kill_until=0, halt_until=0,
                last_sig_t=0, positions=[], eq_hist=[])


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def record_trade(row):
    new = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["coin", "side", "t_sig", "entry", "stop", "exit_t",
                        "kind", "net", "pnl", "notional", "equity_after",
                        "mode"])
        w.writerow(row)


def load_events():
    if os.path.exists(EVENTS):
        return json.load(open(EVENTS))
    fleet_store = pf.EVENTS
    if os.path.exists(fleet_store):          # seed from the paper fleet
        shutil.copy(fleet_store, EVENTS)
        log(f"seeded event store from {fleet_store}")
        return json.load(open(EVENTS))
    return dict(events=[], last_ev={})


def save_events(store):
    tmp = EVENTS + ".tmp"
    json.dump(store, open(tmp, "w"))
    os.replace(tmp, EVENTS)


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
        r = self.ex.market_open(coin, is_buy, sz, None, 0.01)
        return self._fill(r)

    def market_close(self, coin):
        r = self.ex.market_close(coin, None, None, 0.01)
        return self._fill(r)

    def stop_order(self, coin, is_buy, sz, trigger_px):
        # stop-market, reduceOnly; limit px = generous slippage bound
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


# ---------------------------------------------------------------- core
def universe():
    uni = json.load(open(os.path.join(
        os.path.dirname(BOT), "paper", "universe60.json")))
    seen, out = set(), {}
    for coin, sym in uni.items():            # dedupe kPEPE/PEPE -> same symbol
        if sym in seen or coin == "TON":     # TON not listed on HL
            continue
        seen.add(sym)
        out[coin] = sym
    return out


def breakers(st, now):
    """Live-money circuit breakers on top of the research kill-switch.
    Returns True when entries are blocked."""
    if os.path.exists(HALTED):
        return True
    hist = [e for e in st["eq_hist"] if e[0] >= now - 7 * 86_400_000]
    if hist:
        peak7 = max(e[1] for e in hist)
        if st["equity"] / peak7 - 1 < WEEK_DD:
            open(HALTED, "w").write(
                f"7d drawdown breached {WEEK_DD:.0%} at {iso(now)}. "
                "Delete this file to re-enable after re-validation.\n")
            log(f"WEEKLY BREAKER: 7d dd < {WEEK_DD:.0%} — FULL HALT "
                f"(rm bot/HALTED to resume)")
            return "close_all"
        day = [e for e in hist if e[0] >= now - 86_400_000]
        if day and st["equity"] / max(e[1] for e in day) - 1 < DAY_DD:
            if st["halt_until"] < now:
                st["halt_until"] = now + DAY_HALT
                log(f"DAILY BREAKER: 24h dd < {DAY_DD:.0%} — closing all, "
                    f"halt until {iso(st['halt_until'])}")
                return "close_all"
    return st["halt_until"] > now


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
            if gone:                          # stop filled on-exchange
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
            net = pos["side"] * (px / pos["entry"] - 1) - 0.0009
            exit_t = now
        else:
            cnd = klines(uni[coin], limit=min(pos["hold"] + 4, 100),
                         start=pos["t_sig"])
            if cnd is None:
                continue
            ex = check_exit(pos | {"ticker": coin}, cnd)
            if ex is None:
                continue
            net, exit_t, kind = ex
        pnl = pos["notional"] * net
        st["equity"] += pnl
        st["eq_hist"].append([exit_t, st["equity"]])
        st["positions"].remove(pos)
        record_trade([coin, pos["side"], pos["t_sig"], pos["entry"],
                      pos["stop"], exit_t, kind, round(net, 6),
                      round(pnl, 2), round(pos["notional"], 2),
                      round(st["equity"], 2), "live" if hl else "dry"])
        log(f"EXIT {coin} {kind} net {net*100:+.2f}% pnl {pnl:+.2f} "
            f"equity {st['equity']:.2f}")


def close_all(st, uni, hl):
    for pos in list(st["positions"]):
        if hl:
            hl.cancel_all(pos["coin"])
            px, _ = hl.market_close(pos["coin"])
            if px is None:
                continue
            net = pos["side"] * (px / pos["entry"] - 1) - 0.0009
        else:
            k = klines(uni[pos["coin"]], limit=1)
            if not k:
                continue
            net = pos["side"] * (k[-1]["c"] / pos["entry"] - 1) - 0.0009
        pnl = pos["notional"] * net
        st["equity"] += pnl
        now = int(time.time() * 1000)
        st["eq_hist"].append([now, st["equity"]])
        st["positions"].remove(pos)
        record_trade([pos["coin"], pos["side"], pos["t_sig"], pos["entry"],
                      pos["stop"], now, "breaker", round(net, 6),
                      round(pnl, 2), round(pos["notional"], 2),
                      round(st["equity"], 2), "live" if hl else "dry"])
        log(f"BREAKER-CLOSE {pos['coin']} net {net*100:+.2f}%")


def run_signals(st, uni, candles, gate, hl, short_only):
    open_coins = {p["coin"] for p in st["positions"]}
    max_t = st["last_sig_t"]
    for coin, cnd in candles.items():
        if not cnd:
            continue
        side, sig = -1, None
        s_sig = signal(cnd, CFG)
        m_sig = None if short_only else signal_momo(cnd)
        if s_sig and gate["short"]:
            sig = s_sig
        elif m_sig and gate["long"]:
            sig, side = m_sig, 1
        elif s_sig or m_sig:
            t = (s_sig or m_sig)["t_sig"]
            max_t = max(max_t, t)
            if t > st["last_sig_t"]:
                m = f"{gate['m']*100:+.2f}%" if gate["m"] is not None else "n/a"
                log(f"SKIP {coin}: {'short' if s_sig else 'long'} book closed "
                    f"(n={gate['n']}, m={m})")
            continue
        else:
            continue
        max_t = max(max_t, sig["t_sig"])
        if sig["t_sig"] <= st["last_sig_t"]:
            continue
        if coin in open_coins or len(st["positions"]) >= MAX_CONC:
            continue
        if sig["t_sig"] < st["kill_until"]:
            continue
        hist = [e for e in st["eq_hist"]
                if e[0] >= sig["t_sig"] - KILL_LOOKBACK]
        if hist and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
            st["kill_until"] = sig["t_sig"] + KILL_PAUSE
            log(f"KILL-SWITCH: 7d dd < -5%, pause until {iso(st['kill_until'])}")
            continue

        stop = sig["stop"] if side == 1 else sig["hh"]
        sl_dist = abs(stop / sig["entry"] - 1)
        size_eq = min(st["equity"], EQUITY_CAP) if hl else st["equity"]
        notional = min(RISK * size_eq / max(sl_dist, 0.005),
                       NOTIONAL_CAP * size_eq, MAX_NOTIONAL_USD if hl else 1e18)
        entry_px = sig["entry"]
        if hl:
            sz = hl.round_sz(coin, notional / entry_px)
            if sz is None or sz * entry_px < MIN_ORDER_USD:
                log(f"SKIP {coin}: size {sz} below HL minimum")
                continue
            px, filled = hl.market_open(coin, side == 1, sz)
            if px is None:
                continue
            entry_px, notional = px, filled * px
            oid = hl.stop_order(coin, side == -1, filled, stop)
            if oid is None:
                log(f"WARN {coin}: no resting stop on exchange — bot-managed only")
        st["positions"].append(dict(coin=coin, side=side, t_sig=sig["t_sig"],
                                    entry=entry_px, stop=stop,
                                    notional=notional,
                                    hold=MOMO_HOLD if side == 1 else CFG["hold"]))
        open_coins.add(coin)
        log(f"ENTER {'LONG' if side == 1 else 'SHORT'} {coin} @ {entry_px} "
            f"(runup {sig['runup']*100:+.1f}%) stop {stop:.6g} "
            f"({sl_dist*100:.1f}%) notional {notional:.2f} "
            f"{'LIVE' if hl else 'dry'}")
    st["last_sig_t"] = max_t
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= int(time.time() * 1000) - 3 * KILL_LOOKBACK]


def cycle(st, uni, hl, short_only):
    now = int(time.time() * 1000)
    if hl:
        try:
            st["equity"] = hl.equity()
        except Exception as e:
            log(f"WARN equity fetch failed: {e!r} — skipping cycle")
            return
        st["eq_hist"].append([now, st["equity"]])

    with ThreadPoolExecutor(max_workers=6) as ex:
        candles = dict(zip(uni, ex.map(lambda c: klines(uni[c], limit=25), uni)))
    ok = sum(1 for c in candles.values() if c)
    if ok < len(uni) * 0.8:
        log(f"WARN only {ok}/{len(uni)} tickers fetched, skipping cycle")
        return

    store = load_events()
    detect_events(store, candles)
    resolve_events(store, uni)
    save_events(store)
    gate = gate_state(store)

    run_exits(st, uni, hl)
    b = breakers(st, now)
    if b == "close_all":
        close_all(st, hl)
    elif not b:
        run_signals(st, uni, candles, gate, hl, short_only)
    save_state(st)


def status():
    st = load_state()
    g = gate_state(load_events()) if os.path.exists(EVENTS) else None
    print(f"HL BOT  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"equity {st['equity']:.2f} | open {len(st['positions'])} | "
          f"kill_until {iso(st['kill_until']) if st['kill_until'] else '-'} | "
          f"halted {'YES' if os.path.exists(HALTED) else 'no'}")
    if g:
        m = f"{g['m']*100:+.2f}%" if g["m"] is not None else "n/a"
        book = ("SHORT book open" if g["short"] else
                "LONG book open" if g["long"] else "all books FLAT")
        print(f"regime: {book} (n={g['n']}, m={m})")
    for p in st["positions"]:
        print(f"  {p['coin']} {'long' if p['side']==1 else 'short'} "
              f"@ {p['entry']} stop {p['stop']:.6g} since {iso(p['t_sig'])}")
    if os.path.exists(TRADES):
        rows = list(csv.reader(open(TRADES)))[1:]
        nets = [float(r[7]) for r in rows]
        if nets:
            win = sum(1 for n in nets if n > 0) / len(nets) * 100
            print(f"closed {len(nets)} | win {win:.0f}% | "
                  f"avg net {sum(nets)/len(nets)*100:+.3f}%")


def main():
    os.makedirs(BOT, exist_ok=True)
    if "--status" in sys.argv:
        return status()
    short_only = "--short-only" in sys.argv
    live = "--live" in sys.argv
    hl = None
    if live:
        armed = (os.path.exists(ARMED)
                 and open(ARMED).read().strip() == "YES")
        if not (os.environ.get("HL_PRIVATE_KEY")
                and os.environ.get("HL_ACCOUNT") and armed):
            print("LIVE refused. Need HL_PRIVATE_KEY, HL_ACCOUNT, "
                  "and bot/ARMED containing YES. Running DRY instead.")
            live = False
        else:
            hl = HL()
            log(f"LIVE MODE | account {hl.addr[:8]}... | "
                f"equity cap {EQUITY_CAP} | per-trade cap {MAX_NOTIONAL_USD}")
    st = load_state()
    log(f"bot start | mode {'LIVE' if hl else 'dry'} | "
        f"strategy {'gate30-short' if short_only else 'ts30 two-sided'} | "
        f"equity {st['equity']:.2f} | open {len(st['positions'])}")
    uni = universe()
    log(f"universe: {len(uni)} HL-listed coins")
    while True:
        try:
            cycle(st, uni, hl, short_only)
        except Exception as e:
            log(f"ERROR cycle: {e!r}")
        if "--once" in sys.argv:
            break
        now = time.time()
        nxt = (now // 900 + 1) * 900 + 30
        time.sleep(max(nxt - now, 1))


if __name__ == "__main__":
    main()
