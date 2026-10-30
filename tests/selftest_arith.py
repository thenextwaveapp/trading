"""Arithmetic operands — compare spreads and ratios without a dedicated indicator.

An operand can now be {op: add|sub|mul|div, left, right} (symbols +,-,*,/ too),
nestable and with its own offset, so a condition can test e.g. (high - low) /
close > 0.02 or SMA - close > 0. This pins: correct evaluation, nesting, offset,
div-by-zero -> False, lookback/indicator collection through the arithmetic, and
validation of malformed operands.

Run: python3 -m tests.selftest_arith
"""
from core.expr import eval_node
from core.strategy import StrategyError, _collect_indicators, _node_lookback, parse

M15 = 900_000
T0 = 1_700_000_000_000


def mk(n=60):
    # high-low spread = 1 + i%5 ; close rises i%5 above 100
    return [{"t": T0 + i * M15, "o": 100.0, "h": 100.0 + (i % 5),
             "l": 99.0, "c": 100.0 + (i % 5), "v": 10.0} for i in range(n)]


def cond(left, op, right):
    return {"left": left, "op": op, "right": right}


def main():
    ok = True

    def check(c, msg):
        nonlocal ok
        if not c:
            print("FAIL:", msg)
            ok = False

    c = mk()
    i = 13                                   # i%5 == 3 -> spread = 4, close = 103

    # sub: high - low == 4 here
    check(eval_node(c, cond({"op": "sub", "left": {"ind": "high"},
                             "right": {"ind": "low"}}, "eq", 4), i, {}),
          "sub operand (high-low) should equal 4 at i=13")
    # add / mul / div as constants fold too
    check(eval_node(c, cond({"op": "add", "left": 2, "right": 3}, "eq", 5), i, {}),
          "add of constants")
    check(eval_node(c, cond({"op": "mul", "left": {"ind": "close"},
                             "right": 2}, "eq", 206), i, {}),
          "mul close*2 == 206 at i=13 (close 103)")
    check(eval_node(c, cond({"op": "div", "left": {"ind": "high"},
                             "right": {"ind": "low"}}, "gt", 1), i, {}),
          "div high/low should exceed 1")

    # nesting: (high - low) / close == 4/103
    nested = {"op": "div",
              "left": {"op": "sub", "left": {"ind": "high"},
                       "right": {"ind": "low"}},
              "right": {"ind": "close"}}
    check(eval_node(c, cond(nested, "gt", 0.03), i, {})
          and not eval_node(c, cond(nested, "gt", 0.05), i, {}),
          "nested (high-low)/close ~ 0.0388 at i=13")

    # offset on an arithmetic operand shifts the whole expression one bar back
    # i=13 spread 4; i-1=12 spread 3
    off = {"op": "sub", "left": {"ind": "high"}, "right": {"ind": "low"},
           "offset": -1}
    check(eval_node(c, cond(off, "eq", 3), i, {}),
          "offset -1 on arithmetic reads the prior bar's spread (3)")

    # div by zero -> None -> condition False
    check(not eval_node(c, cond({"op": "div", "left": {"ind": "close"},
                                 "right": 0}, "gt", 0), i, {}),
          "division by zero must make the condition False, not crash")

    # lookback + indicator collection recurse through arithmetic
    expr = {"op": "sub",
            "left": {"ind": "SMA", "params": {"timeperiod": 29}},
            "right": {"ind": "close"}}
    check(_node_lookback(cond(expr, "gt", 0)) == 28,
          "lookback must come from the deepest indicator in the arithmetic")
    acc = []
    _collect_indicators(cond(expr, "gt", 0), acc)
    check(set(acc) == {"SMA", "close"},
          f"indicator collection must see both operands, got {acc}")

    # a full parse + backtest runs with an arithmetic entry
    strat = parse({"name": "a", "side": "long", "market": "crypto_perp",
                   "timeframe": "15m",
                   "entry": {"logic": "AND", "children": [cond(nested, "gt", 0.0)]},
                   "exit": {"time_bars": 8, "stop": {"mode": "none"}}})
    from core.backtest import backtest
    check(backtest(strat, c)["stats"]["n"] >= 0, "arithmetic entry should backtest")

    # validation rejects malformed arithmetic
    for bad in ({"op": "pow", "left": {"ind": "close"}, "right": 2},
                {"op": "sub", "left": {"ind": "close"}},          # missing right
                {"op": "sub", "left": {"ind": "nope"}, "right": 1}):  # unknown ind
        try:
            parse({"name": "b", "side": "long", "timeframe": "15m",
                   "entry": {"logic": "AND", "children": [cond(bad, "gt", 0)]},
                   "exit": {"time_bars": 8}})
            check(False, f"malformed arithmetic {bad} must be rejected")
        except StrategyError:
            pass

    if ok:
        print("PASS: arithmetic operands evaluate, nest, offset, guard div-by-"
              "zero, and validate.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
