"""Parameter sweep expansion + per-run results.

Run: python3 -m tests.selftest_sweep
"""
from core.params import default_spec, set_path
from core.service import ep_sweep
from core.sweep import expand_prepared, label_for, prepare_axes

ENTRY = {"logic": "AND", "children": [
    {"left": {"ind": "close"}, "op": "gt", "right": 0},
]}
NEVER = {"logic": "AND", "children": [
    {"left": {"ind": "close"}, "op": "lt", "right": 0},
]}
M15 = 900_000
T0 = 1_700_000_000_000


def candles(n=120):
    return [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
             "c": 100.0 + (i % 5), "v": 10.0} for i in range(n)]


def base_spec():
    spec = set_path(default_spec(), "entry", ENTRY)
    spec = set_path(spec, "exit.stop.mode", "none")
    spec = set_path(spec, "exit.time_bars", 5)
    return spec


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    prepared = prepare_axes([
        {"path": "exit.time_bars", "values": [5, 5, 10]},
        {"path": "side", "values": ["short"]},
    ])
    check(len(prepared[0][1]) == 2, "duplicate axis values should be removed")

    many = prepare_axes([{"path": "exit.time_bars",
                          "values": list(range(1, 101))}])
    variants = list(expand_prepared(base_spec(), many))
    check(len(variants) == 100, "sweeps should not be capped at an arbitrary size")

    body = {"spec": base_spec(), "candles": candles(), "axes": [
        {"path": "exit.time_bars", "values": [5, 10]},
        {"path": "exit.stop.mode", "values": ["none", "hh"]},
    ]}
    code, out = ep_sweep(body)
    check(code == 200 and out.get("ok"), f"sweep should run, got {out.get('error')}")
    check(out.get("count") == 4 and out.get("completed") == 4,
          f"expected 4 completed runs, got {out.get('count')}/{out.get('completed')}")
    check(len({r["label"] for r in out.get("runs", [])}) == 4,
          "each grid point should have a distinct label")
    check(all(r["stats"]["n"] > 0 for r in out.get("runs", [])),
          "every run should produce trades on this tape")
    check(out.get("window", {}).get("source") == "inline",
          "sweep should report the shared data window")

    body = {"spec": base_spec(), "candles": candles(), "axes": [
        {"path": "timing.hours_utc", "values": [[], [0]]},
        {"path": "fresh", "values": [False, True]},
        {"path": "sizing.risk", "values": [0.0075, 0.015]},
    ]}
    code, out = ep_sweep(body)
    check(code == 200 and out.get("count") == 8 and out.get("completed") == 8,
          "int_list, bool and float axes should all expand and run")
    finals = {round((r.get("stats") or {}).get("final_equity", 0), 4)
              for r in out.get("runs", [])}
    check(len(finals) > 1, "different sizing values should change the equity result")
    check(label_for({"sizing.risk": 0.0075}) == "Risk per trade=0.75%",
          "percent axes should be labeled as percentages")

    body = {"spec": base_spec(), "candles": candles(), "axes": [
        {"path": "timeframe", "values": ["15m", "1h"]},
    ]}
    code, out = ep_sweep(body)
    check(code == 200 and out.get("count") == 2 and out.get("completed") == 1,
          "a timeframe sweep should run the base row and reject inline 1h")
    erows = [r for r in out.get("runs", []) if r.get("error")]
    check(len(erows) == 1 and "inline candles" in erows[0]["error"],
          "inline candles should explain the non-base timeframe error")

    never = set_path(base_spec(), "entry", NEVER)
    body = {"spec": base_spec(), "candles": candles(), "axes": [
        {"path": "entry", "values": [ENTRY, NEVER]},
    ]}
    code, out = ep_sweep(body)
    check(code == 200 and out.get("ok"), "condition axes should run")
    ns = sorted(r["stats"]["n"] for r in out.get("runs", []))
    check(ns[0] == 0 and ns[1] > 0, f"condition variants should differ, got {ns}")

    body = {"spec": base_spec(), "candles": candles(), "axes": [
        {"path": "side", "values": ["both"]},
    ]}
    code, out = ep_sweep(body)
    check(code == 200 and out.get("ok") and out.get("completed") == 0,
          "an unsupported value should fail its row, not the whole sweep")
    check(out["runs"][0].get("error") and out["runs"][0].get("issues"),
          "a failed row should carry the capability reason")

    code, out = ep_sweep({"spec": base_spec(), "candles": candles(), "axes": [
        {"path": "nope", "values": [1]},
    ]})
    check(code == 400 and not out.get("ok"), "unknown axes should be rejected")

    code, out = ep_sweep({"spec": base_spec(), "candles": candles(), "axes": [
        {"path": "exit.limit", "values": [0.01]},
    ]})
    check(code == 400 and not out.get("ok"),
          "axes the backtest cannot execute should be rejected up front")

    if ok:
        print("PASS: sweeps expand every grid point, cap-free, with per-run errors")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
