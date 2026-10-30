"""Multi-timeframe + cross-asset operands — causal (no-lookahead) resolution.

An operand can read another candle series via `tf` (other timeframe) and/or
`symbol` (other instrument). The engine aligns that series to the base tape so a
value read at a base bar is always the most recent bar CLOSED at or before the
base bar's close — never a bar still forming. Getting that wrong is lookahead
bias: a backtest that reads the future and can't be reproduced live.

This pins: the alignment is causal, the no-lookahead behavior shows up in
evaluation (a forming aux bar is NOT read), MTF and cross-asset both resolve,
requirements are extracted, base-only bots are unaffected, and the live gate
honestly blocks cross-series until the fetch layer is wired.

Run: python3 -m tests.selftest_multiseries
"""
from core.backtest import backtest, exit_trade
from core.evaluator import align_series, build_aux, entry_signal
from core.expr import eval_node
from core.params import blocking_issues
from core.strategy import parse
from runtime.spec_runtime import covered, new_state, run_exits_spec, run_spec_signals

M15 = 900_000
H1 = 3_600_000
T0 = 0


def base_candles(n):
    return [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
             "c": 100.0, "v": 10.0} for i in range(n)]


def h1_candles(closes):
    return [{"t": T0 + k * H1, "o": c, "h": c + 1.0, "l": c - 1.0, "c": c,
             "v": 10.0} for k, c in enumerate(closes)]


def main():
    ok = True

    def check(c, msg):
        nonlocal ok
        if not c:
            print("FAIL:", msg)
            ok = False

    # --- 1. alignment is causal over the whole tape -------------------------
    base = base_candles(40)
    aux1h = h1_candles([50, 50, 50, 200, 200, 200, 200, 200, 200, 200, 200, 200])
    align = align_series(base, M15, aux1h, H1)
    aux_close = [c["t"] + H1 for c in aux1h]
    causal = True
    for i, c in enumerate(base):
        bc = c["t"] + M15
        k = align[i]
        if k >= 0 and aux_close[k] > bc:                       # read an unclosed bar
            causal = False
        if k + 1 < len(aux1h) and aux_close[k + 1] <= bc:      # missed a closed bar
            causal = False
    check(causal, "alignment must point to the most recent CLOSED aux bar")

    # specific causal boundary: 1h bar k=1 (t 3.6M) closes at 7.2M.
    # base bar i=5 closes at 5.4M -> must still read k=0 (the forming k=1 is off-limits)
    check(align[5] == 0 and align[6] == 0 and align[7] == 1,
          f"align boundary wrong: {align[5], align[6], align[7]}")

    # --- 2. no-lookahead shows up in evaluation -----------------------------
    # condition: the 1h close > 100. k=0..2 are 50 (<=100), k>=3 are 200 (>100).
    node = {"left": {"ind": "close", "tf": "1h"}, "op": "gt", "right": 100}
    aux = build_aux(base, M15, {(None, "1h"): (aux1h, H1)})
    # i=5,6 sit inside the forming higher bars but the last CLOSED 1h bar is k=0
    # (close 50) -> False. If we peeked at the future bar it would be True.
    check(not eval_node(base, node, 5, {}, aux),
          "i=5 must read the last closed 1h bar (50), not the forming one")
    check(not eval_node(base, node, 6, {}, aux), "i=6 same")
    # k=3 (close 200) first closes at 14.4M -> base bar i=15 (closes 14.4M)
    check(eval_node(base, node, 15, {}, aux),
          "i=15 should read the now-closed 1h bar (200) -> True")
    check(not eval_node(base, node, 14, {}, aux),
          "i=14 (13.5M close) must still read a 50-close 1h bar -> False")

    # --- 3. MTF end to end: the gate delays the first entry -----------------
    strat = parse({"name": "mtf", "side": "long", "timeframe": "15m",
                   "entry": {"logic": "AND", "children": [
                       {"left": {"ind": "close"}, "op": "gt", "right": 0},
                       node]},
                   "exit": {"time_bars": 4, "stop": {"mode": "none"}}})
    r = backtest(strat, base, aux_series={(None, "1h"): (aux1h, H1)})
    check(r["stats"]["n"] > 0, "MTF backtest should take trades once the gate opens")
    check(all(t["t_sig"] >= 15 * M15 for t in r["trades"]),
          "no entry may fire before the 1h gate turns true at i=15 (no lookahead)")

    # --- 4. cross-asset: a BTC condition on an ETH base ---------------------
    btc = [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
            "c": (90.0 if i < 20 else 110.0), "v": 10.0} for i in range(40)]
    xnode = {"left": {"ind": "close", "symbol": "BTC"}, "op": "gt", "right": 100}
    xaux = build_aux(base, M15, {("BTC", None): (btc, M15)})
    check(not eval_node(base, xnode, 10, {}, xaux)
          and eval_node(base, xnode, 25, {}, xaux),
          "cross-asset BTC close should gate: <100 early, >100 late")

    # --- 5. requirements extraction -----------------------------------------
    multi = parse({"name": "m", "side": "long", "timeframe": "15m",
                   "entry": {"logic": "AND", "children": [node, xnode]},
                   "exit": {"time_bars": 4}})
    check(multi["_requires"] == [(None, "1h"), ("BTC", None)],
          f"requirements wrong: {multi['_requires']}")
    check(parse({"name": "b", "side": "long", "timeframe": "15m",
                 "entry": {"logic": "AND", "children": [
                     {"left": {"ind": "close"}, "op": "gt", "right": 0}]},
                 "exit": {"time_bars": 4}})["_requires"] == [],
          "a base-only bot must require nothing")

    # --- 6. cross-series is now live-covered (fetch is wired) ---------------
    xspec = {"name": "x", "side": "long", "timeframe": "15m",
             "entry": {"logic": "AND", "children": [
                 {"left": {"ind": "close"}, "op": "gt", "right": 0}, xnode]},
             "exit": {"time_bars": 4, "stop": {"mode": "none"}}}
    check(covered(xspec), "a cross-series bot is live-covered once fetch is wired")
    check(not any(i["id"] == "operand.cross_series"
                  for i in blocking_issues(xspec, "live")),
          "cross-series must not block live anymore")

    # --- 7. base-only bots unaffected by aux plumbing -----------------------
    base_only = parse({"name": "o", "side": "long", "timeframe": "15m",
                       "entry": {"logic": "AND", "children": [
                           {"left": {"ind": "close"}, "op": "gt", "right": 0}]},
                       "exit": {"time_bars": 4, "stop": {"mode": "none"}}})
    s_noaux = entry_signal(base_only, base, 20, {})
    s_aux = entry_signal(base_only, base, 20, {}, build_aux(base, M15, {}))
    check((s_noaux is None) == (s_aux is None),
          "a base-only bot must behave the same with or without aux")

    # --- 8. cross-series inside an exit_conditions tree ---------------------
    # A long with no stop/tp; exit tree = 1h close > 100 (true from base i=15).
    pos = {"entry": 100.0, "hold": 30, "side": 1, "stop": 0.0,
           "t_sig": base[9]["t"] + M15, "i": 9, "interval_ms": M15,
           "exit_conditions": node}
    with_aux = exit_trade(dict(pos), base, 0.00045, 0.0005, aux)
    without = exit_trade(dict(pos), base, 0.00045, 0.0005, None)
    check(with_aux is not None and with_aux[2] == "cond"
          and with_aux[1] == 16 * M15,
          f"exit tree should fire on the 1h gate at i=15, got {with_aux}")
    check(without is not None and without[2] == "time",
          "without aux the cross-series exit operand is None -> no cond exit "
          f"(would have been the silent gap), got {without}")

    # --- 9. live path: run_spec_signals / run_exits_spec with a stub fetch ---
    def flat(n, c):
        return [{"t": T0 + i * M15, "o": c, "h": c + 1.0, "l": c - 1.0, "c": c,
                 "v": 10.0} for i in range(n)]

    eth = flat(20, 100.0)                       # base scan tape (fires base cond)

    def resolve(t):
        return {"BTC": "BTCUSDT"}.get(t)

    def fetch_btc(close):
        series = flat(40, close)                # BTC tape at the given close
        return lambda sym, start, limit, iv: series if sym == "BTCUSDT" else []

    xspec_live = {"name": "x", "side": "long", "timeframe": "15m",
                  "entry": {"logic": "AND", "children": [
                      {"left": {"ind": "close"}, "op": "gt", "right": 0}, xnode]},
                  "exit": {"time_bars": 4, "stop": {"mode": "none"}}}
    st = new_state()
    run_spec_signals("x", xspec_live, st, {"ETH": "ETHUSDT"}, {"ETH": eth},
                     notes=[], fetch=fetch_btc(110.0), resolve=resolve)
    check(len(st["positions"]) == 1 and st["positions"][0]["side"] == 1,
          "live cross-asset: BTC>100 should open a long")
    st = new_state()
    run_spec_signals("x", xspec_live, st, {"ETH": "ETHUSDT"}, {"ETH": eth},
                     notes=[], fetch=fetch_btc(90.0), resolve=resolve)
    check(len(st["positions"]) == 0,
          "live cross-asset: BTC<100 should skip (operand reads the real tape)")

    # MTF live: own symbol on the 1h, fetched via the same path
    mtf_spec = {"name": "m", "side": "long", "timeframe": "15m",
                "entry": {"logic": "AND", "children": [
                    {"left": {"ind": "close"}, "op": "gt", "right": 0},
                    {"left": {"ind": "close", "tf": "1h"}, "op": "gt",
                     "right": 100}]},
                "exit": {"time_bars": 4, "stop": {"mode": "none"}}}
    eth1h = h1_candles([110.0] * 8)
    fetch_1h = lambda sym, start, limit, iv: (
        eth1h if sym == "ETHUSDT" and iv == "1h" else [])
    st = new_state()
    run_spec_signals("m", mtf_spec, st, {"ETH": "ETHUSDT"}, {"ETH": eth},
                     notes=[], fetch=fetch_1h, resolve=resolve)
    check(len(st["positions"]) == 1,
          "live MTF: own-symbol 1h close > 100 should open")

    # cross-series EXIT live: base entry opens, BTC>100 closes it on the tape
    exspec = {"name": "e", "side": "long", "timeframe": "15m",
              "entry": {"logic": "AND", "children": [
                  {"left": {"ind": "close"}, "op": "gt", "right": 0}]},
              "exit": {"time_bars": 30, "stop": {"mode": "none"},
                       "exit_conditions": {"logic": "AND", "children": [xnode]}}}
    btc40 = flat(40, 110.0)
    eth40 = flat(40, 100.0)

    def fetch_both(sym, start, limit, iv):
        if sym == "BTCUSDT":
            return btc40
        if sym == "ETHUSDT":
            return eth40                        # longer tape incl. post-signal bars
        return []

    st = new_state()
    run_spec_signals("e", exspec, st, {"ETH": "ETHUSDT"}, {"ETH": eth},
                     notes=[], fetch=fetch_both, resolve=resolve)
    check(st["positions"] and st["positions"][0].get("exit_requires"),
          "an exit-cross bot must open and carry its exit_requires")
    run_exits_spec("e", st, fetch_both, notes=[], interval="15m", resolve=resolve)
    check(len(st["positions"]) == 0 and st["trades"]
          and st["trades"][-1]["kind"] == "cond",
          "live cross-series EXIT: BTC>100 must close the position on the tape")

    if ok:
        print("PASS: cross-series operands resolve causally (no lookahead), MTF "
              "+ cross-asset + exit trees work in backtest AND live.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
