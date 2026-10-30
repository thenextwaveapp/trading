"""Expression engine — evaluate a condition tree over candles at a bar index.

An operand is one of:
  - a constant (number);
  - an indicator reference:  {"ind": "ROC", "params": {"period": 16}, "offset": 0}
    `offset` reads the series at i+offset (e.g. offset -1 = previous bar).
    Optional "tf" / "symbol" read the indicator off ANOTHER candle series — a
    different timeframe (multi-timeframe) and/or a different instrument
    (cross-asset). That series is supplied in `aux` keyed by (symbol, tf), with a
    per-base-bar alignment index so the value read is always the most recent bar
    CLOSED at or before the base bar's close (causal — no lookahead). Absent
    tf/symbol means the base series, unchanged;
  - an arithmetic operand combining two operands:
    {"op": "sub", "left": <operand>, "right": <operand>, "offset": 0}
    with op in add/sub/mul/div (symbols +,-,*,/ accepted). This lets a condition
    compare a spread or ratio (close - SMA, (high-low)/close, RSI*2) without a
    dedicated indicator. Division by zero yields None (the condition is False).

A condition compares two operands:
    {"left": <operand>, "op": "ge", "right": <operand>}
A group combines nodes:
    {"logic": "AND"|"OR"|"NOT", "children": [<node>, ...]}

Used by both backtest and live. `cache` memoizes computed indicator series
across bars and across conditions within one evaluation pass.
"""
from .indicators import REGISTRY

# comparison operator name + symbol aliases -> canonical name
_OPS = {"lt": "lt", "<": "lt", "gt": "gt", ">": "gt",
        "le": "le", "<=": "le", "ge": "ge", ">=": "ge",
        "eq": "eq", "==": "eq",
        "crosses_above": "crosses_above", "crosses_below": "crosses_below"}

# arithmetic operand op + symbol aliases -> canonical name
_ARITH = {"add": "add", "+": "add", "sub": "sub", "-": "sub",
          "mul": "mul", "*": "mul", "div": "div", "/": "div"}


def _series(candles, ref, cache, prefix=()):
    key = prefix + (ref["ind"], tuple(sorted(ref.get("params", {}).items())))
    if key not in cache:
        cache[key] = REGISTRY[ref["ind"]].fn(candles, **ref.get("params", {}))
    return cache[key]


def _val(candles, operand, i, cache, aux=None):
    if not isinstance(operand, dict):            # constant
        return float(operand)
    if "ind" in operand:                         # indicator reference
        sym, tf = operand.get("symbol"), operand.get("tf")
        if sym is None and tf is None:           # base series
            s = _series(candles, operand, cache)
            j = i + operand.get("offset", 0)
        else:                                    # cross-series (MTF / cross-asset)
            entry = (aux or {}).get((sym, tf))
            if entry is None:                    # series not supplied (e.g. live)
                return None
            j0 = entry["align"][i]               # causal: most recent closed bar
            if j0 < 0:
                return None                      # no aux bar has closed yet
            s = _series(entry["candles"], operand, cache, prefix=(sym, tf))
            j = j0 + operand.get("offset", 0)
        if j < 0 or j >= len(s):
            return None
        return s[j]
    if "op" in operand:                          # arithmetic operand
        op = _ARITH[operand["op"]]
        k = i + operand.get("offset", 0)
        l = _val(candles, operand["left"], k, cache, aux)
        r = _val(candles, operand["right"], k, cache, aux)
        if l is None or r is None:
            return None
        if op == "add":
            return l + r
        if op == "sub":
            return l - r
        if op == "mul":
            return l * r
        return l / r if r != 0 else None         # div by zero -> None
    return None


def eval_condition(candles, cond, i, cache, aux=None):
    op = _OPS[cond["op"]]
    if op in ("crosses_above", "crosses_below"):
        l0 = _val(candles, cond["left"], i, cache, aux)
        r0 = _val(candles, cond["right"], i, cache, aux)
        l1 = _val(candles, cond["left"], i - 1, cache, aux)
        r1 = _val(candles, cond["right"], i - 1, cache, aux)
        if None in (l0, r0, l1, r1):
            return False
        return (l1 <= r1 and l0 > r0) if op == "crosses_above" \
            else (l1 >= r1 and l0 < r0)
    l = _val(candles, cond["left"], i, cache, aux)
    r = _val(candles, cond["right"], i, cache, aux)
    if l is None or r is None:
        return False
    if op == "lt":
        return l < r
    if op == "gt":
        return l > r
    if op == "le":
        return l <= r
    if op == "ge":
        return l >= r
    return l == r


def eval_node(candles, node, i, cache, aux=None):
    if "children" in node:
        return eval_group(candles, node, i, cache, aux)
    return eval_condition(candles, node, i, cache, aux)


def eval_group(candles, group, i, cache, aux=None):
    logic = group.get("logic", "AND")
    kids = group["children"]
    if logic == "AND":
        return all(eval_node(candles, k, i, cache, aux) for k in kids)
    if logic == "OR":
        return any(eval_node(candles, k, i, cache, aux) for k in kids)
    if logic == "NOT":
        return not eval_node(candles, kids[0], i, cache, aux)
    raise ValueError(f"unknown logic {logic!r}")
