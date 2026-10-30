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

A two-sided bot (side="both") carries a book per direction instead of one
entry/exit: entry_long/exit_long and entry_short/exit_short. parse() normalizes
both cases into `_books` — a list of {side, dir, entry, exit, _lookback} — so
the evaluator and backtest iterate books uniformly and never special-case both.

parse() validates the spec (known indicators, legal ops, well-formed tree)
and stamps `_lookback` — the max bars of history any book's entry consumes,
used by the evaluator for its gapless guard.
"""
from datetime import date

from .expr import _ARITH, _OPS
from .indicators import REGISTRY
from .markets import MARKETS, available
from .params import STOP_MODES, normalize_spec, timing_sets
from .timeframes import DEFAULT_TIMEFRAME, interval_ms, TIMEFRAME_VALUES


class StrategyError(ValueError):
    pass


def _collect_operand_inds(o, acc):
    """Collect indicator ids from an operand, recursing through arithmetic."""
    if not isinstance(o, dict):
        return
    if "ind" in o:
        acc.append(o["ind"])
    elif "op" in o:
        _collect_operand_inds(o.get("left"), acc)
        _collect_operand_inds(o.get("right"), acc)


def _collect_indicators(node, acc):
    if "children" in node:
        for c in node["children"]:
            _collect_indicators(c, acc)
        return
    for side in ("left", "right"):
        _collect_operand_inds(node.get(side), acc)


def _collect_operand_requires(o, acc):
    """Collect (symbol, tf) keys for cross-series operands, through arithmetic."""
    if not isinstance(o, dict):
        return
    if "ind" in o:
        sym, tf = o.get("symbol"), o.get("tf")
        if sym is not None or tf is not None:
            acc.add((sym, tf))
    elif "op" in o:
        _collect_operand_requires(o.get("left"), acc)
        _collect_operand_requires(o.get("right"), acc)


def _collect_requires(node, acc):
    if "children" in node:
        for c in node["children"]:
            _collect_requires(c, acc)
        return
    for side in ("left", "right"):
        _collect_operand_requires(node.get(side), acc)


def _operand_lookback(o):
    if isinstance(o, (int, float)):
        return 0
    if not isinstance(o, dict):
        raise StrategyError(f"bad operand: {o!r}")
    if "ind" in o:
        ind = o["ind"]
        if ind not in REGISTRY:
            raise StrategyError(f"unknown indicator: {ind!r}")
        tf = o.get("tf")
        if tf is not None and tf not in TIMEFRAME_VALUES:
            raise StrategyError(f"operand tf {tf!r} is not a supported timeframe")
        sym = o.get("symbol")
        if sym is not None and (not isinstance(sym, str) or not sym):
            raise StrategyError(f"operand symbol must be a non-empty string")
        # A cross-series operand reads another tape, so it does not constrain the
        # BASE gapless/lookback window; its own warmup is handled by the aligned
        # aux series returning None until it has enough history.
        if tf is not None or sym is not None:
            return 0
        return REGISTRY[ind].lookback(o.get("params", {})) \
            + abs(o.get("offset", 0))
    if "op" in o:                                # arithmetic operand
        if o["op"] not in _ARITH:
            raise StrategyError(f"unknown arithmetic op: {o['op']!r}")
        if "left" not in o or "right" not in o:
            raise StrategyError(f"arithmetic operand missing left/right: {o!r}")
        return max(_operand_lookback(o["left"]),
                   _operand_lookback(o["right"])) + abs(o.get("offset", 0))
    raise StrategyError(f"bad operand: {o!r}")


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


def _parse_iso_date(s):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        raise StrategyError(f"timing.dates: bad ISO date {s!r}")


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

    # One-off calendar dates / inclusive ranges, measured at bar close. Each
    # entry is an ISO "YYYY-MM-DD" or a range "YYYY-MM-DD/YYYY-MM-DD". Stamp the
    # parsed (from, to) day ordinals for a cheap membership test in the evaluator.
    dates = timing.get("dates")
    if dates is not None:
        if not isinstance(dates, list):
            raise StrategyError("timing.dates must be a list")
        norm, ords = [], []
        for d in dates:
            if not isinstance(d, str):
                raise StrategyError("timing.dates entries must be ISO strings")
            parts = d.split("/")
            if len(parts) == 1:
                a = b = _parse_iso_date(parts[0])
            elif len(parts) == 2:
                a, b = _parse_iso_date(parts[0]), _parse_iso_date(parts[1])
                if a > b:
                    raise StrategyError(f"timing.dates range out of order: {d!r}")
            else:
                raise StrategyError(f"bad timing.dates entry: {d!r}")
            norm.append(d)
            ords.append((a.toordinal(), b.toordinal()))
        timing["dates"] = norm
        spec["_timing_dates"] = tuple(sorted(ords))


def _validate_exit(ex):
    """Validate one exit object in place and stamp its exit-condition lookback.
    Returns the (defaulted) exit dict."""
    if ex is None:
        ex = {}
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

    # A discretionary exit tree: close the position on the bar it first fires.
    # Validate its shape and stamp its lookback so live can warm the same
    # indicator history the backtest sees (parity).
    ec = ex.get("exit_conditions")
    if ec is not None:
        ex["_exit_lookback"] = _node_lookback(ec)
    return ex


def _build_books(out):
    """Resolve the strategy's directional books — the uniform internal form the
    engine runs. A single-side bot has one book (its `entry`/`exit`); a
    two-sided bot has an `entry_long`/`exit_long` book and an
    `entry_short`/`exit_short` book. Each book carries its own validated exit
    and entry lookback, so the evaluator/backtest never special-case `both`."""
    side = out["side"]
    if side == "both":
        plan = (("long", 1, "entry_long", "exit_long"),
                ("short", -1, "entry_short", "exit_short"))
        for _, _, ek, _ in plan:
            if ek not in out:
                raise StrategyError(
                    "side 'both' requires entry_long and entry_short")
    else:
        if "entry" not in out:
            raise StrategyError("strategy missing required field: 'entry'")
        plan = ((side, 1 if side == "long" else -1, "entry", "exit"),)
    books = []
    for sd, dr, ek, xk in plan:
        ex = _validate_exit(out.get(xk))
        out[xk] = ex
        books.append({"side": sd, "dir": dr, "entry": out[ek], "exit": ex,
                      "_lookback": _node_lookback(out[ek])})
    return books


def parse(spec):
    if "side" not in spec:
        raise StrategyError("strategy missing required field: 'side'")
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
    out["_books"] = _build_books(out)
    out["_lookback"] = max(b["_lookback"] for b in out["_books"])
    # cross-series data the bot needs: (symbol, tf) keys referenced by any
    # operand (symbol None = base symbol, tf None = base tf). The fetch layer
    # loads these; an empty set means the bot runs on its base tape alone.
    reqs = set()
    for book in out["_books"]:
        _collect_requires(book["entry"], reqs)
        ec = book["exit"].get("exit_conditions")
        if ec:
            _collect_requires(ec, reqs)
    out["_requires"] = sorted(reqs, key=lambda x: (x[0] or "", x[1] or ""))
    out.setdefault("fresh", False)
    hours, days = timing_sets(out)
    out["_timing_hours"] = hours
    out["_timing_days"] = days

    # market capability: every indicator the strategy uses, across every book's
    # entry and exit tree, must be computable on its market, or it can't be saved
    market = out.get("market")
    if market is not None:
        if market not in MARKETS:
            raise StrategyError(f"unknown market: {market!r}")
        m = MARKETS[market]
        refs = []
        for book in out["_books"]:
            _collect_indicators(book["entry"], refs)
            ec = book["exit"].get("exit_conditions")
            if ec:
                _collect_indicators(ec, refs)
        for ind in refs:
            if not available(REGISTRY[ind], m):
                missing = sorted(set(REGISTRY[ind].inputs) - set(m.provides))
                raise StrategyError(
                    f"indicator {ind!r} needs {missing}, which market "
                    f"{market!r} does not provide")
    return out
