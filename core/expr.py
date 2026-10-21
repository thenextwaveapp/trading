"""Expression engine — evaluate a condition tree over candles at a bar index.

An operand is either a constant (number) or an indicator reference:
    {"ind": "ROC", "params": {"period": 16}, "offset": 0}
`offset` reads the series at i+offset (e.g. offset -1 = previous bar).

A condition compares two operands:
    {"left": <operand>, "op": "ge", "right": <operand>}
A group combines nodes:
    {"logic": "AND"|"OR"|"NOT", "children": [<node>, ...]}

This same evaluator is used by both backtest and live — the honesty
invariant. `cache` memoizes computed indicator series across bars and across
conditions within one evaluation pass.
"""
from .indicators import REGISTRY

# operator name + symbol aliases -> canonical name
_OPS = {"lt": "lt", "<": "lt", "gt": "gt", ">": "gt",
        "le": "le", "<=": "le", "ge": "ge", ">=": "ge",
        "eq": "eq", "==": "eq",
        "crosses_above": "crosses_above", "crosses_below": "crosses_below"}


def _series(candles, ref, cache):
    key = (ref["ind"], tuple(sorted(ref.get("params", {}).items())))
    if key not in cache:
        cache[key] = REGISTRY[ref["ind"]].fn(candles, **ref.get("params", {}))
    return cache[key]


def _val(candles, operand, i, cache):
    if not isinstance(operand, dict):            # constant
        return float(operand)
    s = _series(candles, operand, cache)
    j = i + operand.get("offset", 0)
    if j < 0 or j >= len(s):
        return None
    return s[j]


def eval_condition(candles, cond, i, cache):
    op = _OPS[cond["op"]]
    if op in ("crosses_above", "crosses_below"):
        l0 = _val(candles, cond["left"], i, cache)
        r0 = _val(candles, cond["right"], i, cache)
        l1 = _val(candles, cond["left"], i - 1, cache)
        r1 = _val(candles, cond["right"], i - 1, cache)
        if None in (l0, r0, l1, r1):
            return False
        return (l1 <= r1 and l0 > r0) if op == "crosses_above" \
            else (l1 >= r1 and l0 < r0)
    l = _val(candles, cond["left"], i, cache)
    r = _val(candles, cond["right"], i, cache)
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


def eval_node(candles, node, i, cache):
    if "children" in node:
        return eval_group(candles, node, i, cache)
    return eval_condition(candles, node, i, cache)


def eval_group(candles, group, i, cache):
    logic = group.get("logic", "AND")
    kids = group["children"]
    if logic == "AND":
        return all(eval_node(candles, k, i, cache) for k in kids)
    if logic == "OR":
        return any(eval_node(candles, k, i, cache) for k in kids)
    if logic == "NOT":
        return not eval_node(candles, kids[0], i, cache)
    raise ValueError(f"unknown logic {logic!r}")
