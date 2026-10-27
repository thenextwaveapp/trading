"""DB-fleet runtime — exits resolve against the post-signal tape.

Run: python3 -m tests.selftest_spec_runtime
"""
from core import parse
from core.backtest import build_position
from runtime.spec_runtime import new_state, run_exits_spec

M15 = 900_000
H1 = 3_600_000
T0 = 1_793_000_000_000

SPEC = {
    "name": "unit",
    "side": "short",
    "entry": {"logic": "AND", "children": [
        {"op": "gt", "left": {"ind": "close", "offset": 0, "params": {}},
         "right": 0}]},
    "exit": {"stop": {"mode": "none", "param": 0, "window": 16},
             "time_bars": 1},
    "universe": "unit",
}


def candles(n=40):
    return [{"t": T0 + i * M15, "o": 100.0 + i, "h": 101.0 + i,
             "l": 99.0 + i, "c": 100.5 + i, "v": 10.0} for i in range(n)]


def main():
    c = candles()
    strat = parse(SPEC)
    i = 30
    sig = {"t_sig": c[i]["t"] + M15, "entry": c[i]["c"], "i": i, "side": -1}
    pos = build_position(strat, c, i, sig)
    pos.update(ticker="TEST", symbol="TESTUSDT", notional=1000.0)

    st = new_state()
    st["positions"] = [pos]

    def fetch(symbol, start, limit, interval):
        assert interval == "15m"
        return [x for x in c if x["t"] >= start][:limit]

    run_exits_spec("unit", st, fetch, notes=[])

    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    check(not st["positions"], "position should close on the fetched tape")
    check(len(st.get("trades") or []) == 1, "exit should be recorded")
    if st.get("trades"):
        tr = st["trades"][0]
        check(tr["exit_t"] == c[i + 1]["t"] + M15,
              "time exit should use the first post-signal bar")
        check(tr["kind"] == "time", f"expected time exit, got {tr['kind']}")
        check(abs(st["equity"] - (10_000.0 + tr["pnl"])) < 0.01,
              "equity should include the trade pnl")

    h1_spec = {**SPEC, "timeframe": "1h"}
    h1 = [{"t": T0 + i * H1, "o": 100.0 + i, "h": 101.0 + i,
           "l": 99.0 + i, "c": 100.5 + i, "v": 10.0} for i in range(40)]
    h1_strat = parse(h1_spec)
    h1_sig = {"t_sig": h1[i]["t"] + H1, "entry": h1[i]["c"], "i": i, "side": -1}
    h1_pos = build_position(h1_strat, h1, i, h1_sig)
    h1_pos.update(ticker="TEST", symbol="TESTUSDT", notional=1000.0)

    h1_state = new_state()
    h1_state["positions"] = [h1_pos]

    def fetch_h1(symbol, start, limit, interval):
        assert interval == "1h"
        return [x for x in h1 if x["t"] >= start][:limit]

    run_exits_spec("unit-h1", h1_state, fetch_h1, notes=[], interval="1h")
    check(not h1_state["positions"], "1h position should close on the fetched tape")
    check(len(h1_state.get("trades") or []) == 1, "1h exit should be recorded")
    if h1_state.get("trades"):
        check(h1_state["trades"][0]["exit_t"] == h1[i + 1]["t"] + H1,
              "1h time exit should use the first post-signal bar")

    if ok:
        print("PASS: DB-fleet exits resolve on the fetched post-signal tape")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
