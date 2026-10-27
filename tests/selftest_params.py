"""Parameter registry + capability map.

Run: python3 -m tests.selftest_params
"""
import json

from core.export_catalog import build
from core.params import (FEATURES, GROUPS, PARAM_BY_KEY, PARAMS,
                         blocking_issues, default_spec, get_path, set_path,
                         spec_issues)
from core.strategy import StrategyError, parse
from core.timeframes import DEFAULT_TIMEFRAME, TIMEFRAMES, interval_ms

ENTRY = {"logic": "AND", "children": [
    {"left": {"ind": "close"}, "op": "gt", "right": 0},
]}


def base_spec():
    return set_path(default_spec(), "entry", ENTRY)


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    keys = [p.key for p in PARAMS]
    check(len(keys) == len(set(keys)), "parameter keys must be unique")
    check(set(PARAM_BY_KEY) == set(keys), "PARAM_BY_KEY must match PARAMS")
    group_ids = {g["id"] for g in GROUPS}
    check(all(p.group in group_ids for p in PARAMS),
          "every parameter must belong to a declared group")
    check(all(p.kind in ("int", "float", "bool", "enum", "int_list",
                         "string", "condition") for p in PARAMS),
          "unknown parameter kind in registry")
    check(len({f["id"] for f in FEATURES}) == len(FEATURES),
          "feature ids must be unique")

    spec = base_spec()
    parsed = parse(spec)
    check(parsed["side"] == "short", "default side should be short")
    check(parsed["_timing_hours"] == frozenset(),
          "empty timing should mean every hour")
    check(not blocking_issues(parsed, "backtest"),
          "default spec should be backtestable")
    check(parsed["_timeframe"] == DEFAULT_TIMEFRAME
          and parsed["_interval_ms"] == interval_ms(DEFAULT_TIMEFRAME),
          "default spec should use the default candle size")

    for tf, _label, ms in TIMEFRAMES:
        got = parse(set_path(spec, "timeframe", tf))
        check(got["_timeframe"] == tf and got["_interval_ms"] == ms == interval_ms(tf),
              f"{tf} should parse and carry its interval")
    try:
        parse(set_path(spec, "timeframe", "1M"))
    except StrategyError:
        pass
    else:
        check(False, "1M must be rejected because calendar months are not fixed-width")

    for key in ("sizing.risk", "sizing.notional_cap", "exit.stop.param",
                "exit.take_profit", "exit.limit"):
        check(PARAM_BY_KEY[key].percent,
              f"{key} should be presented as a percentage")

    both = set_path(spec, "side", "both")
    check(any(i["id"] == "side.both" for i in blocking_issues(both, "backtest")),
          "side both must be blocked until direction is modeled")

    trail = set_path(spec, "exit.stop.mode", "trail")
    check(any(i["id"] == "stop.trail" for i in blocking_issues(trail, "backtest")),
          "legacy stop trail must be blocked, not silently ignored")

    trailing = set_path(spec, "exit.trailing", {"k": 3.0, "natr": 24})
    parse(trailing)
    check(not blocking_issues(trailing, "backtest"),
          "trailing should be usable in the lab")
    check(any(i["id"] == "exit.trailing" for i in blocking_issues(trailing, "live")),
          "trailing must block live until parity is pinned")

    limit = set_path(spec, "exit.limit", 0.01)
    check(any(i["id"] == "exit.limit" for i in blocking_issues(limit, "backtest")),
          "resting limits must block the spec backtest")

    exits = set_path(spec, "exit.exit_conditions", ENTRY)
    check(any(i["id"] == "exit.exit_conditions"
              for i in blocking_issues(exits, "backtest")),
          "unexecuted exit conditions must block")

    filtered = set_path(spec, "filters", [{"kind": "btc_bear"}])
    parse(filtered)
    check(not blocking_issues(filtered, "backtest"),
          "filters are real live gates and should not block the lab")
    check(any(i["id"] == "filters" for i in spec_issues(filtered, "backtest")),
          "filters must warn that the backtest is unfiltered")

    weighted = set_path(spec, "sizing.weight", 0.5)
    check(not blocking_issues(weighted, "backtest"),
          "ignored weight should not block")
    check(any(i["id"] == "sizing.weight" and i["status"] == "ignored"
              for i in spec_issues(weighted, "backtest")),
          "non-unit weight must be surfaced as ignored")

    timed = set_path(set_path(spec, "timing.hours_utc", [3, 3]),
                     "timing.days_utc", [0])
    parsed_timed = parse(timed)
    check(parsed_timed["_timing_hours"] == frozenset({3}),
          "timing hours should be deduped")
    check(parsed_timed["_timing_days"] == frozenset({0}),
          "timing days should be parsed")

    for path, value, label in (
        ("timing.hours_utc", [24], "hour 24"),
        ("timing.days_utc", [7], "day 7"),
        ("timing.hours_utc", ["3"], "string hour"),
        ("timing.hours_utc", [True], "boolean hour"),
    ):
        try:
            parse(set_path(spec, path, value))
        except StrategyError:
            pass
        else:
            check(False, f"{label} should fail validation")

    moved = set_path({"a": {"b": 1}}, "a.b", None)
    check(get_path(moved, "a.b") is None, "set_path(None) should remove a path")
    check(get_path(set_path({}, "x.y", 2), "x.y") == 2,
          "set_path should create missing objects")

    cat = build()
    check(len(cat["spec_params"]) == len(PARAMS),
          "catalog should export every parameter")
    check(all("percent" in p for p in cat["spec_params"]),
          "catalog should export percent presentation metadata")
    check(len(cat["spec_features"]) == len(FEATURES),
          "catalog should export every feature")
    try:
        json.dumps(cat)
    except TypeError as e:
        check(False, f"catalog must be JSON serializable: {e}")

    if ok:
        print(f"PASS: {len(PARAMS)} params, {len(FEATURES)} capability "
              "features, defaults + gates agree")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
