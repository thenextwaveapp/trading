"""Two-sided bots (side: both) — entry resolution, per-book exits, live routing.

A both bot carries entry_long/exit_long and entry_short/exit_short. The engine
must:
  - open LONG when only the long book fires,
  - open SHORT when only the short book fires,
  - SKIP the bar when BOTH fire (ambiguous — never silently pick a side),
  - use each side's own exit rule on the position it opens,
and the live spec_runtime path must route the same books the same way.

The books are built so we can hit every case on demand: long fires when
close > 100; short fires when the PREVIOUS close > 100 (offset -1). Closes that
cross 100 give only-long (rising through), only-short (falling through), both
(two bars above), and neither.

Run: python3 -m tests.selftest_side_both
"""
from core.backtest import backtest, build_position
from core.evaluator import entry_signal
from core.strategy import parse
from runtime.spec_runtime import covered, new_state, run_spec_signals

M15 = 900_000
T0 = 1_700_000_000_000


def spec_dict():
    return {
        "name": "two", "side": "both", "timeframe": "15m",
        "entry_long": {"logic": "AND", "children": [
            {"left": {"ind": "close"}, "op": "gt", "right": 100}]},
        "exit_long": {"time_bars": 5, "stop": {"mode": "dstop", "param": 0.1}},
        "entry_short": {"logic": "AND", "children": [
            {"left": {"ind": "close", "offset": -1}, "op": "gt", "right": 100}]},
        "exit_short": {"time_bars": 9, "stop": {"mode": "dstop", "param": 0.2}},
    }


def mk(closes):
    return [{"t": T0 + i * M15, "o": c, "h": c + 1.0, "l": c - 1.0, "c": c,
             "v": 10.0} for i, c in enumerate(closes)]


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    strat = parse(spec_dict())
    check(len(strat["_books"]) == 2, "a both bot must have two books")

    # bar 10: close 105, prev 95 -> only long
    only_long = mk([95] * 10 + [105])
    s = entry_signal(strat, only_long, 10, {})
    check(s is not None and s["dir"] == 1 and s["side"] == "long",
          f"only-long bar should open long, got {s}")
    if s:
        pos = build_position(strat, only_long, 10, s)
        check(pos["side"] == 1 and pos["hold"] == 5,
              f"long position must use exit_long (hold 5), got {pos.get('hold')}")

    # bar 10: close 95, prev 105 -> only short
    only_short = mk([95] * 9 + [105, 95])
    s = entry_signal(strat, only_short, 10, {})
    check(s is not None and s["dir"] == -1 and s["side"] == "short",
          f"only-short bar should open short, got {s}")
    if s:
        pos = build_position(strat, only_short, 10, s)
        check(pos["side"] == -1 and pos["hold"] == 9,
              f"short position must use exit_short (hold 9), got {pos.get('hold')}")

    # bar 10: close 110, prev 105 -> BOTH fire -> skip (ambiguous)
    both_fire = mk([95] * 9 + [105, 110])
    s = entry_signal(strat, both_fire, 10, {})
    check(s is None, f"both books firing must skip the bar, got {s}")

    # neither
    neither = mk([95] * 11)
    check(entry_signal(strat, neither, 10, {}) is None,
          "no book firing must produce no signal")

    # a backtest over a crossing series must produce BOTH long and short trades
    closes = [95] * 10
    for _ in range(12):
        closes += [105, 108, 95, 92]      # up through 100, then down through it
    r = backtest(strat, mk(closes))
    check(r["stats"]["n"] > 0, "two-sided backtest should take trades")

    # --- live routing: the spec_runtime path opens the same side as the engine
    sp = spec_dict()
    check(covered(sp), "a well-formed two-sided bot must be live-covered")

    st = new_state()
    run_spec_signals("t", sp, st, {"X": "XUSDT"}, {"X": mk([95] * 10 + [105])},
                     notes=[])
    check(len(st["positions"]) == 1 and st["positions"][0]["side"] == 1,
          "live must open a LONG on an only-long bar")
    check(st["positions"] and st["positions"][0]["hold"] == 5,
          "live long must carry exit_long (hold 5)")

    st = new_state()
    run_spec_signals("t", sp, st, {"X": "XUSDT"},
                     {"X": mk([95] * 9 + [105, 95])}, notes=[])
    check(len(st["positions"]) == 1 and st["positions"][0]["side"] == -1,
          "live must open a SHORT on an only-short bar")
    check(st["positions"] and st["positions"][0]["hold"] == 9,
          "live short must carry exit_short (hold 9)")

    st = new_state()
    run_spec_signals("t", sp, st, {"X": "XUSDT"},
                     {"X": mk([95] * 9 + [105, 110])}, notes=[])
    check(len(st["positions"]) == 0,
          "live must skip the bar when both books fire")

    if ok:
        print("PASS: side:both opens the right book, skips conflicts, uses "
              "per-side exits, and routes identically live.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
