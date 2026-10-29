"""Challenges — lock-set enforcement, predicates, and judges.

Run: python3 -m tests.selftest_challenges
"""
from core.challenges import (JUDGES, build_entry, check_locks, rank,
                             score_twin, validate_entry)


def template():
    """A full, locked spec: RSI(14) < 30 on ETH/1h, long, 3% stop, 6% TP."""
    return {
        "name": "Template",
        "side": "long",
        "market": "crypto_perp",
        "universe": "fleet-60",
        "timeframe": "1h",
        "entry": {"logic": "AND", "children": [
            {"left": {"ind": "RSI", "params": {"period": 14}},
             "op": "lt", "right": 30},
        ]},
        "exit": {"time_bars": 48, "stop": {"mode": "dstop", "param": 0.03},
                 "take_profit": 0.06},
        "sizing": {"risk": 0.01, "notional_cap": 0.25},
    }


# the one open hole: the RSI threshold (pick X)
THRESHOLD = "entry.children.0.right"


def _fake(total_net_pct, max_dd, n, nets=None):
    r = {"stats": {"total_net_pct": total_net_pct, "max_drawdown": max_dd, "n": n}}
    if nets is not None:
        r["trades"] = [{"net": x} for x in nets]
    return r


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
            print(f"  FAIL: {msg}")

    t = template()

    # --- the hole is open: a legal threshold pick passes -------------------
    entry = build_entry(t, {THRESHOLD: 25}, [THRESHOLD])
    check(entry["entry"]["children"][0]["right"] == 25, "edit applied to the hole")
    good, err = validate_entry(t, entry, [THRESHOLD])
    check(good, f"legal threshold entry should pass, got {err!r}")

    # a different name must never read as a lock violation
    entry["name"] = "My Entry"
    good, err = validate_entry(t, entry, [THRESHOLD])
    check(good, f"renaming an entry must be allowed, got {err!r}")

    # --- everything else is locked -----------------------------------------
    try:
        build_entry(t, {"exit.time_bars": 12}, [THRESHOLD])
        check(False, "editing a locked path should raise")
    except ValueError as e:
        check("exit.time_bars" in str(e), f"error should name the locked path, got {e!r}")

    # a candidate that changed a locked leaf directly is rejected, named
    bad = build_entry(t, {THRESHOLD: 25}, [THRESHOLD])
    bad["exit"]["take_profit"] = 0.10
    good, err = validate_entry(t, bad, [THRESHOLD])
    check(not good and "exit.take_profit" in (err or ""),
          f"locked take_profit change should reject naming the path, got {err!r}")

    # changing the universe is locked unless universe is the hole
    uni = build_entry(t, {THRESHOLD: 25}, [THRESHOLD])
    uni["universe"] = "fleet-10"
    good, err = validate_entry(t, uni, [THRESHOLD])
    check(not good and "universe" in (err or ""),
          f"universe is locked for a threshold challenge, got {err!r}")
    good, err = validate_entry(t, uni, [THRESHOLD, "universe"])
    check(good, f"universe challenge should allow a universe change, got {err!r}")

    # --- predicates --------------------------------------------------------
    rng = [{"kind": "range", "path": THRESHOLD, "min": 10, "max": 40}]
    good, _ = validate_entry(t, build_entry(t, {THRESHOLD: 25}, [THRESHOLD]),
                             [THRESHOLD], rng)
    check(good, "in-range threshold passes the range predicate")
    good, err = validate_entry(t, build_entry(t, {THRESHOLD: 90}, [THRESHOLD]),
                               [THRESHOLD], rng)
    check(not good, "out-of-range threshold fails the range predicate")

    # shape: node cap
    big = build_entry(t, {}, ["entry"])
    big["entry"]["children"] = [big["entry"]["children"][0]] * 9
    good, err = validate_entry(t, big, ["entry"], [{"kind": "max_nodes", "max": 8}])
    check(not good and "node" in (err or ""), f"node cap should trip, got {err!r}")

    # restriction: a banned indicator
    banned = [{"kind": "indicators_not_in", "banned": ["RSI"]}]
    good, err = validate_entry(t, build_entry(t, {}, ["entry"]), ["entry"], banned)
    check(not good and "RSI" in (err or ""), f"banned RSI should trip, got {err!r}")

    # restriction: distinct-indicator count (One Eye = exactly one)
    good, _ = validate_entry(t, build_entry(t, {}, ["entry"]), ["entry"],
                             [{"kind": "distinct_indicators", "exact": 1}])
    check(good, "single-indicator entry satisfies exact=1")

    # constraint: No Weather Allowed
    wx = build_entry(t, {}, ["entry"])
    wx["condition_filter"] = {"btc_trend": "up"}
    good, err = validate_entry(t, wx, ["entry"], [{"kind": "no_weather"}])
    check(not good, "a Weather gate should fail No Weather Allowed")

    # --- Fix #1: a spelled-out default must not read as a lock violation ----
    # candidate carries `fresh: false` (a harmless default t omits) + a legal pick
    indep = {k: v for k, v in t.items() if k != "name"}
    indep["fresh"] = False
    indep["entry"] = {"logic": "AND", "children": [
        {"left": {"ind": "RSI", "params": {"period": 14}}, "op": "lt", "right": 22}]}
    good, err = validate_entry(t, indep, [THRESHOLD])
    check(good, f"a default-valued key must not trip the lock, got {err!r}")

    # --- Fix #2: shape challenges (AST must match a pattern) ---------------
    def entry_of(children, logic="AND"):
        e = build_entry(t, {}, ["entry"])
        e["entry"] = {"logic": logic, "children": children}
        return e

    # Pure Cross — SMA crosses EMA (both Overlap Studies)
    cross = entry_of([{"left": {"ind": "SMA", "params": {"period": 10}},
                       "op": "crosses_above",
                       "right": {"ind": "EMA", "params": {"period": 30}}}])
    good, err = validate_entry(t, cross, ["entry"],
                               [{"kind": "shape_match", "shape": "pure_cross"}])
    check(good, f"SMA x EMA should satisfy pure_cross, got {err!r}")
    # the locked template (RSI < const) is NOT a cross
    good, err = validate_entry(t, build_entry(t, {}, ["entry"]), ["entry"],
                               [{"kind": "shape_match", "shape": "pure_cross"}])
    check(not good, "a threshold entry must fail pure_cross")

    # Two-Factor — RSI (momentum) AND VOL_RATIO (volume), different families
    tf = entry_of([
        {"left": {"ind": "RSI", "params": {"period": 14}}, "op": "gt", "right": 60},
        {"left": {"ind": "VOL_RATIO", "params": {"period": 20}}, "op": "gt", "right": 2},
    ])
    good, err = validate_entry(t, tf, ["entry"],
                               [{"kind": "shape_match", "shape": "two_factor"}])
    check(good, f"RSI AND VOL_RATIO should satisfy two_factor, got {err!r}")
    # two factors from the SAME family must fail
    same = entry_of([
        {"left": {"ind": "RSI", "params": {"period": 14}}, "op": "gt", "right": 60},
        {"left": {"ind": "ROC", "params": {"period": 10}}, "op": "gt", "right": 0},
    ])
    good, err = validate_entry(t, same, ["entry"],
                               [{"kind": "shape_match", "shape": "two_factor"}])
    check(not good, "two momentum factors must fail two_factor")

    # Single Candle — WICK_FRAC + VOL_RATIO, offset 0 only
    sc = entry_of([
        {"left": {"ind": "WICK_FRAC", "params": {"period": 16}}, "op": "gt", "right": 0.6},
        {"left": {"ind": "VOL_RATIO", "params": {"period": 20}}, "op": "gt", "right": 1.8},
    ])
    good, err = validate_entry(t, sc, ["entry"],
                               [{"kind": "shape_match", "shape": "single_candle"}])
    check(good, f"WICK/VOL current-bar entry should satisfy single_candle, got {err!r}")
    sc_off = entry_of([{"left": {"ind": "WICK_FRAC", "params": {"period": 16}, "offset": -1},
                        "op": "gt", "right": 0.6}])
    good, err = validate_entry(t, sc_off, ["entry"],
                               [{"kind": "shape_match", "shape": "single_candle"}])
    check(not good, "a lookback offset must fail single_candle")

    # --- judges ------------------------------------------------------------
    entries = [
        {"id": "a", "result": _fake(10.0, -0.20, 30)},
        {"id": "b", "result": _fake(25.0, -0.40, 12)},
        {"id": "c", "result": _fake(4.0, -0.05, 40)},
    ]
    board = {s["id"]: s for s in rank(entries, "return")}
    check(board["b"]["place"] == 1, "return: biggest total wins")
    check(board["c"]["place"] == 3, "return: smallest total last")

    board = {s["id"]: s for s in rank(entries, "low_drawdown", {"trade_floor": 10})}
    check(board["c"]["place"] == 1, "low_drawdown: shallowest DD wins")
    board = {s["id"]: s for s in rank(entries, "low_drawdown", {"trade_floor": 20})}
    check(board["b"]["place"] is None, "low_drawdown: below trade floor is ineligible")

    # median_distance: closest to the median return wins
    board = {s["id"]: s for s in rank(entries, "median_distance")}
    check(board["a"]["place"] == 1, "median_distance: median return wins (10 is the median)")

    # profit_factor needs trades
    pf = [{"id": "p", "result": _fake(0, 0, 3, nets=[0.05, 0.05, -0.02])}]
    board = rank(pf, "profit_factor")
    check(abs(board[0]["score"] - (0.10 / 0.02)) < 1e-9, "profit_factor = gross win / gross loss")

    # Twin: scored by the worse book
    worse = score_twin(_fake(20.0, -0.1, 10), _fake(-5.0, -0.3, 8), "return")
    check(worse == -5.0, "twin takes the worse of the two directions")

    # every named judge resolves
    check(set(JUDGES) >= {"return", "calmar", "profit_factor", "low_drawdown",
                          "fewest_trades_positive", "median_distance"},
          "judge registry is complete")

    if ok:
        print(f"PASS: lock-set, {len(JUDGES)} judges, predicates enforced")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
