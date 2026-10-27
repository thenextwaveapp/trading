"""Strategy spec — parse + validate a strategy dict, compute its lookback.

A Strategy is the composable object that replaces "engine + variant":

    {
      "name": str,
      "side": "long" | "short" | "both",
      "market": str,                 # e.g. "crypto_perp"
      "universe": str,               # e.g. "fleet-60"
      "fresh": bool,                 # fire only on the bar the entry becomes true
      "entry": <ConditionGroup>,
      "timing": {hours_utc, days_utc},  # optional signal windows
      "exit":  {time_bars, stop:{mode,param}, take_profit, trailing, ...},
      "sizing": {risk, notional_cap, weight}
    }

parse() validates the spec (known indicators, legal ops, well-formed tree)
and stamps `_lookback` — the max bars of history the entry consumes, used by
the evaluator for its gapless guard.
"""
from .expr import _OPS
from .indicators import REGISTRY
from .markets import MARKETS, available
from .params import STOP_MODES, normalize_spec, timing_sets
from .timeframes import DEFAULT_TIMEFRAME, interval_ms, TIMEFRAME_VALUES


class StrategyError(ValueError):
    pass


def _collect_indicators(node, acc):
    if "children" in node:
        for c in node["children"]:
            _collect_indicators(c, acc)
        return
    for side in ("left", "right"):
        o = node.get(side)
        if isinstance(o, dict) and "ind" in o:
            acc.append(o["ind"])


def _operand_lookback(o):
    if isinstance(o, (int, float)):
        return 0
    if not isinstance(o, dict) or "ind" not in o:
        raise StrategyError(f"bad operand: {o!r}")
    ind = o["ind"]
    if ind not in REGISTRY:
        raise StrategyError(f"unknown indicator: {ind!r}")
    return REGISTRY[ind].lookback(o.get("params", {})) + abs(o.get("offset", 0))


def _node_lookback(n):
    if not isinstance(n, dict):
        raise StrategyError(f"bad node: {n!r}")
    if "children" in n:
        if n.get("logic", "AND") not in ("AND", "OR", "NOT"):
            raise StrategyError(f"unknown logic: {n.get('logic')!r}")
        if not n["children"]:
            raise StrategyError("empty condition group")
        return max(_node_lookback(c) for c in n["children"])
    if n.get("op") not in _OPS:
        raise StrategyError(f"unknown operator: {n.get('op')!r}")
    if "left" not in n or "right" not in n:
        raise StrategyError(f"condition missing left/right: {n!r}")
    return max(_operand_lookback(n["left"]), _operand_lookback(n["right"]))


def _validate_timing(spec):
    timing = spec.get("timing")
    if timing is None:
        return
    if not isinstance(timing, dict):
        raise StrategyError("timing must be an object")
    for key, hi in (("hours_utc", 23), ("days_utc", 6)):
        vals = timing.get(key, [])
        if vals is None:
            vals = []
        if not isinstance(vals, list):
            raise StrategyError(f"timing.{key} must be a list")
        for v in vals:
            if isinstance(v, bool) or not isinstance(v, int):
                raise StrategyError(f"timing.{key} values must be integers")
            if v < 0 or v > hi:
                raise StrategyError(
                    f"timing.{key} value {v} outside 0..{hi}")
        timing[key] = sorted(set(vals))


def _validate_exit(spec):
    ex = spec.setdefault("exit", {})
    if not isinstance(ex, dict):
        raise StrategyError("exit must be an object")
    hold = ex.get("time_bars", 16)
    if isinstance(hold, bool) or not isinstance(hold, int) or hold < 1:
        raise StrategyError("exit.time_bars must be an integer >= 1")
    ex["time_bars"] = hold

    stop = ex.get("stop")
    if stop is not None:
        if not isinstance(stop, dict):
            raise StrategyError("exit.stop must be an object")
        mode = stop.get("mode", "none")
        if mode not in STOP_MODES:
            raise StrategyError(f"unknown stop mode: {mode!r}")
        if "window" in stop:
            w = stop["window"]
            if isinstance(w, bool) or not isinstance(w, int) or w < 1:
                raise StrategyError("exit.stop.window must be an integer >= 1")
        if "param" in stop and not isinstance(stop["param"], (int, float)):
            raise StrategyError("exit.stop.param must be numeric")

    tr = ex.get("trailing")
    if tr is not None:
        if not isinstance(tr, dict):
            raise StrategyError("exit.trailing must be an object")
        k, natr = tr.get("k"), tr.get("natr")
        if not isinstance(k, (int, float)) or k <= 0:
            raise StrategyError("exit.trailing.k must be > 0")
        if isinstance(natr, bool) or not isinstance(natr, int) or natr < 1:
            raise StrategyError("exit.trailing.natr must be an integer >= 1")

    tp = ex.get("take_profit")
    if tp is not None and (not isinstance(tp, (int, float)) or tp < 0):
        raise StrategyError("exit.take_profit must be >= 0")


def parse(spec):
    for req in ("side", "entry"):
        if req not in spec:
            raise StrategyError(f"strategy missing required field: {req!r}")
    if spec["side"] not in ("long", "short", "both"):
        raise StrategyError(f"bad side: {spec['side']!r}")
    out = normalize_spec(spec)
    timeframe = out.get("timeframe", DEFAULT_TIMEFRAME)
    if timeframe not in TIMEFRAME_VALUES:
        raise StrategyError(
            f"unsupported candle size: {timeframe!r}; choose one of "
            f"{', '.join(TIMEFRAME_VALUES)}")
    out["timeframe"] = timeframe
    out["_timeframe"] = timeframe
    out["_interval_ms"] = interval_ms(timeframe)
    _validate_timing(out)
    _validate_exit(out)
    out["_lookback"] = _node_lookback(out["entry"])
    out.setdefault("fresh", False)
    hours, days = timing_sets(out)
    out["_timing_hours"] = hours
    out["_timing_days"] = days

    # market capability: every indicator the strategy uses must be computable
    # on its market, or it can't be saved
    market = out.get("market")
    if market is not None:
        if market not in MARKETS:
            raise StrategyError(f"unknown market: {market!r}")
        m = MARKETS[market]
        refs = []
        _collect_indicators(out["entry"], refs)
        exit_conds = out.get("exit", {}).get("exit_conditions")
        if exit_conds:
            _collect_indicators(exit_conds, refs)
        for ind in refs:
            if not available(REGISTRY[ind], m):
                missing = sorted(set(REGISTRY[ind].inputs) - set(m.provides))
                raise StrategyError(
                    f"indicator {ind!r} needs {missing}, which market "
                    f"{market!r} does not provide")
    return out
