"""Run a canonical core Strategy spec in the live fleet.

Unlike paper_fleet.run_signals(), which dispatches on a hand-coded `engine` key,
this module runs from a spec: entries come from core.entry_signal and the
position (stop/tp) from core.build_position — the same functions the backtester
runs, so a bot trades live exactly as it backtested (core/selftest.py for
entries, core/selftest_exit.py for exits).

Scope: only specs with proven live==backtest parity — side long/short/both,
stop mode hh/dstop/none/sig, no resting-limit order, not `partial`. A two-sided
bot runs both its books; direction and exit come from whichever fires (ties skip
the bar). Cross-series operands (multi-timeframe / cross-asset) are covered: the
fleet resolves each referenced symbol (pf_coins), fetches its tape, and aligns it
causally per bar — entry and exit alike. A trailing stop is covered: its NATR
fraction is measured at entry by the shared
core.build_position, so the ratchet is identical live and in backtest. A
discretionary exit_conditions tree is covered: it runs through the same
core.exit_trade live as in backtest, with its indicator history warmed from the
same pre-entry bars. covered() is the gate; anything it rejects stays on the
legacy run_signals path. Covers pump_short
(base/strict/fast/slow/loose/hold24/buf2/vol3/veto/wick30) and capit_long.

Exits are unchanged: paper_fleet.run_exits() drives check_exit() over the
position dict built here, and check_exit == core.exit_trade.

The Weather gate (`pf_bots.condition_filter`) is applied at entry: the current
BTC volatility/trend cell must be one the Builder selected, using the terciles
persisted from the training window (core.conditions.cell_at).

Sizing & account logic (kill-switch, concurrency, dedupe) are reproduced from
run_signals verbatim so the equity math is identical; they live here, not core,
because they are live-account concerns, not strategy logic.
"""
import time

from core import parse, entry_signal
from core import db as coredb
from core.backtest import build_position, exit_trade
from core.conditions import cell_at
from core.evaluator import build_aux
from core.strategy import _collect_requires
from core.timeframes import DAY_MS, DEFAULT_TIMEFRAME, interval_ms
from .paper_trader import (RISK, NOTIONAL_CAP, MAX_CONC, START_EQUITY,
                          TAKER, SLIP, KILL_DD, KILL_LOOKBACK, KILL_PAUSE)

# How many bars of a cross-series tape to fetch per cycle — enough for an
# indicator's warm-up plus alignment against the base scan window.
_AUX_BARS = 250


def _cross_aux(reqs, base, base_ms, base_tf, own_symbol, resolve, fetch, cache):
    """Build the evaluator `aux` for cross-series operands: for each required
    (symbol, tf) — symbol None means this instrument, tf None means the base tf —
    resolve the exchange symbol, fetch that tape (cached per (symbol, tf) across
    the cycle), and align it causally to `base`. An unresolved or empty series is
    dropped, so the operand reads None (False) — never stale or fabricated data."""
    series_by_key = {}
    for sym, tf in reqs:
        rsym = resolve(sym) if sym else own_symbol
        if not rsym:
            continue
        rtf = tf or base_tf
        ck = (rsym, rtf)
        if ck not in cache:
            cache[ck] = fetch(rsym, None, _AUX_BARS, rtf) or []
        if cache[ck]:
            series_by_key[(sym, tf)] = (cache[ck], interval_ms(rtf))
    return build_aux(base, base_ms, series_by_key) if series_by_key else None

M15 = 900_000

# stop modes with proven live==backtest parity (core.build_position + check_exit)
_COVERED_STOPS = {"hh", "dstop", "none", "sig"}


def covered(spec):
    """True if this spec can run live with proven parity. Any feature not pinned
    by a differential test disqualifies the bot, keeping it on the legacy engine
    rather than trading it unverified."""
    try:
        if spec.get("partial"):
            return False
        if spec.get("side") not in ("long", "short", "both"):
            return False
        strat = parse(spec)                         # validates + builds _books
        for book in strat["_books"]:                # every book must be covered
            ex = book["exit"] or {}
            if ex.get("limit") is not None:         # resting-order path (capit_lim)
                return False
            stop = (ex.get("stop") or {}).get("mode", "none")
            if stop not in _COVERED_STOPS:          # excludes legacy trail / ext
                return False
        return True
    except Exception:
        return False


def _capit_sl_basis(cnd, i, step=M15):
    """2*NATR24 sizing basis for no-stop longs, computed from the same candles
    the signal fired on — reproduces signal_capit()'s sl_basis exactly so
    capit positions are sized identically to the legacy engine. On a non-15m
    tape the window is the same 24 hours, converted to bars."""
    window = max(2, round(DAY_MS / int(step or M15)))
    if i < window - 1:
        return 0.02                                  # not enough tape; safe default
    trs = [max(cnd[j]["h"], cnd[j - 1]["c"]) - min(cnd[j]["l"], cnd[j - 1]["c"])
           for j in range(i - window + 1, i + 1)]
    natr = (sum(trs) / window) / cnd[i]["c"]
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


def _weather_ok(weather, btc, t_sig):
    """Apply the bot's Weather gate: only enter when the current BTC regime is
    one of the cells selected at deploy time. Older gates without persisted
    terciles cannot be reproduced and are treated as open (none are live)."""
    if not weather or not weather.get("restrict"):
        return True, None
    cells = weather.get("cells") or []
    if not cells:
        return True, None
    lo, hi = weather.get("vol_lo"), weather.get("vol_hi")
    if lo is None or hi is None:
        return True, None
    if not btc:
        return False, "weather gate: no BTC data"
    cell = cell_at(btc, t_sig, lo, hi)
    if cell is None:
        return False, "weather gate: BTC history too short"
    key = f"{cell[0]}:{cell[1]}"
    if key not in cells:
        return False, f"weather gate: {key} not selected"
    return True, None


def run_spec_signals(name, spec, st, universe, candles, *, gate=None,
                     weather=None, btc=None, log=lambda *_: None, notes=None,
                     fetch=None, resolve=None):
    """Entry pass for one spec-driven bot. Mutates `st` (positions, equity
    bookkeeping, kill-switch, last_sig_t) exactly as run_signals does. `notes`
    is the shared feed-event list; `log` the fleet logger. Exits are handled
    elsewhere by run_exits().

    `fetch`/`resolve` supply cross-series data (multi-timeframe / cross-asset):
    fetch(symbol, start, limit, tf) -> candles, resolve(ticker) -> exchange
    symbol. Absent (or a bot with no cross-series operands) means base-tape
    only, exactly as before."""
    notes = notes if notes is not None else []
    strat = parse(spec)
    reqs = strat.get("_requires") or []
    base_tf = strat.get("_timeframe", DEFAULT_TIMEFRAME)
    base_ms = strat.get("_interval_ms", M15)
    aux_cache = {}                                  # per-cycle cross-series fetches
    resolve = resolve or (lambda _t: None)

    open_tk = {p["ticker"] for p in st["positions"]} \
        | {o["ticker"] for o in st.get("orders", [])}
    max_t = st["last_sig_t"]

    for tk, cnd in candles.items():
        if not cnd:
            continue
        i = len(cnd) - 1
        aux = _cross_aux(reqs, cnd, base_ms, base_tf, universe.get(tk),
                         resolve, fetch, aux_cache) \
            if reqs and fetch is not None else None
        sig = entry_signal(strat, cnd, i, None, aux)
        if sig is None:
            continue
        # direction and stop mode come from the book that fired (a two-sided
        # bot can open long on one bar and short on another).
        side = sig["dir"]
        stop_mode = (sig["_book"]["exit"].get("stop") or {}).get("mode", "none")
        max_t = max(max_t, sig["t_sig"])
        if sig["t_sig"] <= st["last_sig_t"]:
            continue

        ok, why = _filters_ok(spec, tk, gate)
        if not ok:
            if why:
                log(f"[{name}] SKIP {tk}: {why}")
            continue
        ok, why = _weather_ok(weather, btc, sig["t_sig"])
        if not ok:
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
        # if the firing book's exit tree reads another series, remember what it
        # needs so the exit pass can fetch and align the same data.
        ec = (sig["_book"]["exit"] or {}).get("exit_conditions")
        if ec:
            er = set()
            _collect_requires(ec, er)
            if er:
                pos["exit_requires"] = sorted(
                    er, key=lambda x: (x[0] or "", x[1] or ""))

        if stop_mode == "none" or stop == 0.0:
            basis = _capit_sl_basis(cnd, i, strat.get("_interval_ms", M15))
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


def run_exits_spec(name, st, fetch, *, notes, interval=DEFAULT_TIMEFRAME,
                   log=lambda *_: None, resolve=None):
    """Resolve open positions via core.exit_trade (== legacy check_exit, proven
    in selftest_exit). `fetch(symbol, start, limit, interval) -> candles` supplies the
    post-signal tape; the engine passes its real klines fetcher, tests a stub.
    `resolve(ticker) -> exchange symbol` lets a cross-series exit tree read
    another instrument, aligned to the same post-signal tape."""
    resolve = resolve or (lambda _t: None)
    for pos in list(st["positions"]):
        # An exit-condition tree needs its indicators warmed with the same
        # pre-entry history the backtest saw, so fetch `exit_lookback` bars
        # before t_sig. Positions without one keep the exact legacy fetch
        # (start at t_sig) so their parity is untouched. exit_trade bisects by
        # t_sig, so the extra leading bars only feed indicator warm-up.
        L = pos.get("exit_lookback", 0) if pos.get("exit_conditions") else 0
        step = pos.get("interval_ms", M15)
        start_t = pos["t_sig"] - (L + 1) * step if L else pos["t_sig"]
        limit = min(pos["hold"] + 8 + ((L + 1) if L else 0), 1500)
        cnd = fetch(pos["symbol"], start_t, limit, interval)
        if not cnd:
            continue
        # `i` indexes the entry scan's candle list, while `cnd` is a fresh
        # fetch starting at t_sig. Drop it so exit_trade locates the first
        # post-signal bar by timestamp instead of indexing past the slice.
        tape_pos = {k: v for k, v in pos.items() if k != "i"}
        # if the exit tree reads another series, fetch + align it to this tape
        er = pos.get("exit_requires")
        aux = _cross_aux(er, cnd, step, interval, pos["symbol"], resolve, fetch,
                         {}) if er else None
        ex = exit_trade(tape_pos, cnd, TAKER, SLIP, aux)
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


def _bot_interval(spec):
    try:
        return parse(spec).get("_timeframe", DEFAULT_TIMEFRAME)
    except Exception:
        return None


def _candles_for(candles, interval):
    """Support both the legacy flat {ticker: bars} map (15m) and the new
    per-candle-size {interval: {ticker: bars}} map."""
    if not candles:
        return {}
    sample = next(iter(candles.values()), None)
    if isinstance(sample, list):
        return candles if interval == DEFAULT_TIMEFRAME else {}
    return candles.get(interval) or {}


def run_fleet(bots, states, candles, universes, *, fetch, gate=None,
              notes=None, log=lambda *_: None):
    """One cycle over the DB-sourced fleet. For each bot: resolve exits, then
    scan entries from its spec over its own universe's tickers only, never a
    shared global set. `bots` is [{id, name, spec}] from load_fleet();
    `universes` is {bot_id: {ticker: binance_symbol}} from pf_universes;
    `candles` is {ticker: series} fetched for the union. A bot whose universe
    didn't resolve ({} / missing) manages open positions only, opens none."""
    notes = notes if notes is not None else []
    btc = _candles_for(candles, DEFAULT_TIMEFRAME).get("BTC")
    # resolve every cross-asset ticker any bot references (e.g. "BTC") to its
    # exchange symbol, once per cycle, from the same pf_coins table universes use.
    want = set()
    for bot in bots:
        try:
            for sym, _tf in parse(bot["spec"]).get("_requires", []):
                if sym:
                    want.add(sym)
        except Exception:
            pass
    sym_map = coredb.coin_symbols(want) if want else {}
    resolve = lambda t: sym_map.get(t)
    for bot in bots:
        st = states.setdefault(bot["id"], new_state())
        iv = _bot_interval(bot["spec"])
        if not iv:
            log(f"[{bot['name']}] SKIP: spec has an unsupported candle size")
            continue
        bot_candles = _candles_for(candles, iv)
        bot_fetch = lambda sym, start, limit, _iv=iv: fetch(
            sym, start, limit, _iv)
        run_exits_spec(bot["name"], st, bot_fetch, notes=notes,
                       interval=iv, log=log, resolve=resolve)
        uni = universes.get(bot["id"]) or {}
        if not uni:
            log(f"[{bot['name']}] SKIP entries: universe did not resolve")
            continue
        if covered(bot["spec"]):
            scoped = {tk: bot_candles.get(tk) for tk in uni
                      if bot_candles.get(tk)}
            run_spec_signals(bot["name"], bot["spec"], st, uni, scoped,
                             gate=gate, weather=bot.get("condition_filter"),
                             btc=btc, log=log, notes=notes,
                             fetch=bot_fetch, resolve=resolve)
    return notes
