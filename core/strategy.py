"""Strategy spec — parse + validate a strategy dict, compute its lookback.

A Strategy is the composable object that replaces "engine + variant":

    {
      "name": str,
      "side": "long" | "short" | "both",
      "market": str,                 # e.g. "crypto_perp"
      "universe": str,               # e.g. "fleet-60"
      "fresh": bool,                 # fire only on the bar the entry becomes true
      "entry": <ConditionGroup>,
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


def parse(spec):
    for req in ("side", "entry"):
        if req not in spec:
            raise StrategyError(f"strategy missing required field: {req!r}")
    if spec["side"] not in ("long", "short", "both"):
        raise StrategyError(f"bad side: {spec['side']!r}")
    out = dict(spec)
    out["_lookback"] = _node_lookback(spec["entry"])
    out.setdefault("fresh", False)

    # market capability: every indicator the strategy uses must be computable
    # on its market, or it can't be saved (the honesty invariant, in schema)
    market = spec.get("market")
    if market is not None:
        if market not in MARKETS:
            raise StrategyError(f"unknown market: {market!r}")
        m = MARKETS[market]
        refs = []
        _collect_indicators(spec["entry"], refs)
        exit_conds = spec.get("exit", {}).get("exit_conditions")
        if exit_conds:
            _collect_indicators(exit_conds, refs)
        for ind in refs:
            if not available(REGISTRY[ind], m):
                missing = sorted(set(REGISTRY[ind].inputs) - set(m.provides))
                raise StrategyError(
                    f"indicator {ind!r} needs {missing}, which market "
                    f"{market!r} does not provide")
    return out
