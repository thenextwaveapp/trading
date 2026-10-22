"""The weld, live side — run a canonical core Strategy spec in the live fleet.

paper_fleet's run_signals() dispatches on a hand-coded `engine` key and computes
entries with signal()/signal_capit()/signal_momo(). This module does the same job
from a *spec*: entries come from core.entry_signal and the position (stop/tp) from
core.build_position — the identical functions the backtester runs, so a bot
trades live exactly as it backtested (proven: core/selftest.py for entries,
core/selftest_exit.py for exits).

Scope — the honest subset. We only run a spec whose every feature has proven
live==backtest parity: side long/short (not both), stop mode hh/dstop/none, no
trailing/sig/ext stop, no resting-limit order, not `partial`. covered() is the
gate; anything it rejects stays on the legacy run_signals path (dual-engine
transition). That covers pump_short (base/strict/fast/slow/loose/hold24/buf2/
vol3/veto/wick30) and capit_long — the validated edges and the bulk of variants.

Exits are unchanged: paper_fleet.run_exits() already drives check_exit() over the
position dict we build here, and check_exit == core.exit_trade (selftest_exit).

Sizing & account logic (kill-switch, concurrency, dedupe) are reproduced from
run_signals verbatim so the equity math is identical; they live here, not in
core, because they are live-account concerns, not strategy logic.
"""
import time

from core import parse, entry_signal
from core.backtest import build_position, exit_trade
from .paper_trader import (RISK, NOTIONAL_CAP, MAX_CONC, START_EQUITY,
                          TAKER, SLIP, KILL_DD, KILL_LOOKBACK, KILL_PAUSE)

M15 = 900_000

# stop modes with proven live==backtest parity (core.build_position + check_exit)
_COVERED_STOPS = {"hh", "dstop", "none", "sig"}


def covered(spec):
    """True if this spec can run live with proven parity. Conservative: any
    feature we haven't pinned with a differential test disqualifies the bot,
    which keeps it on the legacy engine rather than trading it unverified."""
    try:
        if spec.get("partial"):
            return False
        if spec.get("side") not in ("long", "short"):
            return False
        exit_ = spec.get("exit") or {}
        if exit_.get("trailing"):
            return False
        if exit_.get("limit") is not None:          # resting-order path (capit_lim)
            return False
        stop = (exit_.get("stop") or {}).get("mode", "none")
        if stop not in _COVERED_STOPS:              # excludes trail / sig / ext
            return False
        parse(spec)                                 # must validate (known inds/ops)
        return True
    except Exception:
        return False


def _capit_sl_basis(cnd, i):
    """2*NATR24 sizing basis for no-stop longs, computed from the same candles
    the signal fired on — reproduces signal_capit()'s sl_basis exactly so
    capit positions are sized identically to the legacy engine."""
    if i < 96:
        return 0.02                                  # not enough tape; safe default
    trs = [max(cnd[j]["h"], cnd[j - 1]["c"]) - min(cnd[j]["l"], cnd[j - 1]["c"])
           for j in range(i - 95, i + 1)]
    natr = (sum(trs) / 96) / cnd[i]["c"]
    return max(2 * natr, 0.005)


def _filters_ok(spec, tk, gate):
    """Apply spec.filters (btc_bear / regime_veto / universe) — the spec form
    of run_signals' cfg.btc_bear / cfg.veto / cfg.only gates. Returns
    (ok, skip_reason)."""
    for f in spec.get("filters") or []:
        kind = f.get("kind")
        if kind == "universe" and f.get("only") and tk not in f["only"]:
            return False, None                       # silent: not in this bot's set
        if kind == "btc_bear":
            if not (gate and gate.get("bear") is True):
                why = ("BTC data unavailable" if not gate
                       or gate.get("bear") is None else "BTC not in bear regime")
                return False, f"{why}"
        if kind == "regime_veto":
            m = gate.get("m") if gate else None
            thr = f.get("threshold")
            if m is not None and m == m and thr is not None and m > thr:
                return False, (f"regime veto — dial {m*100:+.2f}% "
                               f"> +{thr*100:.0f}%")
    return True, None


def run_spec_signals(name, spec, st, universe, candles, *, gate=None,
                     log=lambda *_: None, notes=None):
    """Entry pass for one spec-driven bot. Mutates `st` (positions, equity
    bookkeeping, kill-switch, last_sig_t) exactly as run_signals does. `notes`
    is the shared feed-event list; `log` the fleet logger. Exits are handled
    elsewhere by run_exits()."""
    notes = notes if notes is not None else []
    strat = parse(spec)
    side = 1 if strat["side"] == "long" else -1
    stop_mode = ((spec.get("exit") or {}).get("stop") or {}).get("mode", "none")

    open_tk = {p["ticker"] for p in st["positions"]} \
        | {o["ticker"] for o in st.get("orders", [])}
    max_t = st["last_sig_t"]

    for tk, cnd in candles.items():
        if not cnd:
            continue
        i = len(cnd) - 1
        sig = entry_signal(strat, cnd, i)
        if sig is None:
            continue
        max_t = max(max_t, sig["t_sig"])
        if sig["t_sig"] <= st["last_sig_t"]:
            continue

        ok, why = _filters_ok(spec, tk, gate)
        if not ok:
            if why:
                log(f"[{name}] SKIP {tk}: {why}")
            continue
        if tk in open_tk:
            log(f"[{name}] SKIP {tk}: position already open")
            continue
        if len(st["positions"]) >= MAX_CONC:
            log(f"[{name}] SKIP {tk}: {MAX_CONC} positions open")
            continue
        if sig["t_sig"] < st["kill_until"]:
            continue
        hist = [e for e in st["eq_hist"] if e[0] >= sig["t_sig"] - KILL_LOOKBACK]
        if hist and st["equity"] / max(e[1] for e in hist) - 1 < KILL_DD:
            st["kill_until"] = sig["t_sig"] + KILL_PAUSE
            log(f"[{name}] KILL-SWITCH: 7d drawdown < -5%")
            notes.append(dict(kind="kill", v=name))
            continue

        # position (stop/tp) straight from core — same object the backtest built
        pos = build_position(strat, cnd, i, sig)
        entry, stop = pos["entry"], pos["stop"]

        if stop_mode == "none" or stop == 0.0:
            basis = _capit_sl_basis(cnd, i)          # 2*NATR24, like signal_capit
        else:
            basis = abs(stop / entry - 1)
        notional = min(RISK * st["equity"] / max(basis, 0.005),
                       NOTIONAL_CAP * st["equity"])

        pos.update(ticker=tk, symbol=universe[tk], notional=notional)
        st["positions"].append(pos)
        open_tk.add(tk)
        runup = sig.get("runup", 0.0)
        log(f"[{name}] ENTER {'LONG' if side == 1 else 'SHORT'} {tk} "
            f"@ {entry} stop {stop:.6g} notional {notional:.2f}")
        notes.append(dict(kind="enter", v=name, tk=tk, side=side,
                          px=entry, runup=runup))

    st["last_sig_t"] = max_t
    st["eq_hist"] = [e for e in st["eq_hist"]
                     if e[0] >= int(time.time() * 1000) - 2 * KILL_LOOKBACK]


def new_state():
    """A bot's paper account: own $10k equity, positions, kill-switch, log."""
    return dict(equity=START_EQUITY, kill_until=0, last_sig_t=0,
                positions=[], eq_hist=[], orders=[], trades=[])


def run_exits_spec(name, st, fetch, *, notes, log=lambda *_: None):
    """Resolve open positions via core.exit_trade (== legacy check_exit, proven
    in selftest_exit). `fetch(symbol, start, limit) -> candles` supplies the
    post-signal tape; the engine passes its real klines fetcher, tests a stub."""
    for pos in list(st["positions"]):
        cnd = fetch(pos["symbol"], pos["t_sig"], min(pos["hold"] + 8, 250))
        if not cnd:
            continue
        ex = exit_trade(pos, cnd, TAKER, SLIP)
        if ex is None:
            continue
        net, exit_t, kind = ex
        pnl = pos["notional"] * net
        st["equity"] += pnl
        st["eq_hist"].append([exit_t, st["equity"]])
        st["positions"].remove(pos)
        st.setdefault("trades", []).append(
            dict(ticker=pos["ticker"], t_sig=pos["t_sig"], entry=pos["entry"],
                 stop=pos["stop"], exit_t=exit_t, kind=kind, net=round(net, 6),
                 pnl=round(pnl, 2), notional=round(pos["notional"], 2),
                 equity=round(st["equity"], 2)))
        log(f"[{name}] EXIT {pos['ticker']} {kind} {net*100:+.2f}% "
            f"pnl {pnl:+.2f} equity {st['equity']:.2f}")
        notes.append(dict(kind="exit", v=name, tk=pos["ticker"],
                          net=net, pnl=pnl))


def run_fleet(bots, states, candles, universes, *, fetch, gate=None,
              notes=None, log=lambda *_: None):
    """One cycle over the DB-sourced fleet. For each bot: resolve exits, then
    scan entries from its spec — but only over ITS OWN universe's tickers, never
    a shared global set. `bots` is [{id, name, spec}] from load_fleet();
    `universes` is {bot_id: {ticker: binance_symbol}} resolved from pf_universes;
    `candles` is {ticker: series} fetched for the union. A bot whose universe
    didn't resolve ({} / missing) does NOT open new positions — it only manages
    what's already open. No founder-universe fallback."""
    notes = notes if notes is not None else []
    for bot in bots:
        st = states.setdefault(bot["id"], new_state())
        run_exits_spec(bot["name"], st, fetch, notes=notes, log=log)
        uni = universes.get(bot["id"]) or {}
        if not uni:
            log(f"[{bot['name']}] SKIP entries: universe did not resolve")
            continue
        if covered(bot["spec"]):
            scoped = {tk: candles[tk] for tk in uni if candles.get(tk)}
            run_spec_signals(bot["name"], bot["spec"], st, uni, scoped,
                             gate=gate, log=log, notes=notes)
    return notes
