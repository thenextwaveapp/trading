"""Prediction markets — resolution settlement, not continuous price.

A prediction contract trades a close-only implied probability and settles to a
1/0 outcome at expiry. This pins the engine's resolution path:

  - flat, close-only, irregular bars still fire entries (the crypto liveness /
    gapless guards are relaxed for resolution markets, and the settled bar is
    never an entry);
  - a bet buys the contract for its side — YES at prob p, NO at 1-p — and
    settles to 1/0: net is the return on that contract price, both legs' fee out;
  - all four win/lose combinations are correct;
  - sizing is a flat fraction of equity (no stop distance to risk against);
  - volume indicators are unavailable on a close-only market.

Run: python3 -m tests.selftest_prediction
"""
from core.backtest import PRED_STAKE, backtest
from core.markets import MARKETS, available, is_resolution
from core.indicators import REGISTRY
from core.strategy import parse

STEP = 900_000
T0 = 1_700_000_000_000
FEE = 2 * 0.0 + 0.01            # prediction CostModel(taker=0, slip=0.01)
ENTRY = {"logic": "AND", "children": [
    {"left": {"ind": "close"}, "op": "gt", "right": 0}]}


def spec(side, exit_=None):
    return parse({"name": "p", "side": side, "market": "prediction",
                  "timeframe": "15m", "entry": ENTRY,
                  "exit": exit_ or {"time_bars": 64, "stop": {"mode": "none"}}})


def series(prob, outcome, n=12):
    """n flat probability bars, then a settlement bar (res=1/0)."""
    bars = [{"t": T0 + i * STEP, "o": prob, "h": prob, "l": prob,
             "c": prob, "v": 0.0} for i in range(n)]
    bars.append({"t": T0 + n * STEP, "o": outcome, "h": outcome, "l": outcome,
                 "c": outcome, "v": 0.0, "res": True})
    return bars


def main():
    ok = True

    def check(c, msg):
        nonlocal ok
        if not c:
            print("FAIL:", msg)
            ok = False

    check(is_resolution("prediction"), "prediction must be a resolution market")

    # YES at 0.40 that resolves YES -> payout 1 on a 0.40 contract
    r = backtest(spec("long"), series(0.40, 1.0))
    check(len(r["trades"]) == 1, f"one bet expected, got {len(r['trades'])}")
    if r["trades"]:
        t = r["trades"][0]
        check(t["kind"] == "settle", f"should settle, got {t['kind']!r}")
        check("size_frac" in t and abs(t["size_frac"] - PRED_STAKE) < 1e-12,
              "prediction trade carries a flat stake fraction")
        check(abs(t["net"] - (1.0 / 0.40 - 1 - FEE)) < 1e-9,
              f"YES win net wrong: {t['net']}")

    # all four win/lose corners
    corners = [
        ("long",  0.40, 1.0, 1.0 / 0.40 - 1 - FEE),   # YES, resolves YES: win
        ("long",  0.40, 0.0, 0.0 / 0.40 - 1 - FEE),   # YES, resolves NO:  -1-fee
        ("short", 0.40, 0.0, 1.0 / 0.60 - 1 - FEE),   # NO at 0.60 wins
        ("short", 0.40, 1.0, 0.0 / 0.60 - 1 - FEE),   # NO loses
    ]
    for side, p, outcome, want in corners:
        tr = backtest(spec(side), series(p, outcome))["trades"]
        got = tr[0]["net"] if tr else None
        check(got is not None and abs(got - want) < 1e-9,
              f"{side} p={p} outcome={outcome}: net {got} != {want}")

    # sizing: one YES win moves equity by exactly stake * net off $10k
    st = backtest(spec("long"), series(0.40, 1.0))["stats"]
    exp = 10_000.0 * PRED_STAKE * (1.0 / 0.40 - 1 - FEE)
    check(abs(st["final_equity"] - (10_000.0 + exp)) < 1e-6,
          f"flat-stake equity wrong: {st['final_equity']}")

    # early exit: an exit_conditions tree closes at the live prob before expiry
    exit_ec = {"time_bars": 64, "stop": {"mode": "none"},
               "exit_conditions": {"logic": "AND", "children": [
                   {"left": {"ind": "close"}, "op": "ge", "right": 0.75}]}}
    bars = ([{"t": T0 + i * STEP, "o": 0.40, "h": 0.40, "l": 0.40,
              "c": 0.40, "v": 0.0} for i in range(12)]
            + [{"t": T0 + 12 * STEP, "o": 0.80, "h": 0.80, "l": 0.80,
                "c": 0.80, "v": 0.0}]                       # prob jumps to 0.80
            + [{"t": T0 + 13 * STEP, "o": 1.0, "h": 1.0, "l": 1.0,
                "c": 1.0, "v": 0.0, "res": True}])
    tr = backtest(spec("long", exit_ec), bars)["trades"]
    check(tr and tr[0]["kind"] == "cond"
          and abs(tr[0]["net"] - (0.80 / 0.40 - 1 - FEE)) < 1e-9,
          f"exit_conditions should close at prob 0.80, got {tr and tr[0]}")

    # capability: a close-only market exposes no volume indicators
    m = MARKETS["prediction"]
    check(not available(REGISTRY["OBV"], m),
          "OBV (needs volume) must be unavailable on prediction")
    check(available(REGISTRY["close"], m),
          "close must be available on prediction")

    # data adapter: symbol routing + the pure prob-history -> candles shaping
    from core.service import (_is_prediction_symbol, _is_equity_symbol,
                              _prediction_candles)
    check(_is_prediction_symbol("POLY:0xabc")
          and _is_prediction_symbol("KALSHI:PRES-24"),
          "POLY:/KALSHI: symbols must route to the prediction fetch")
    check(not _is_equity_symbol("POLY:0xabc"),
          "a prediction symbol must not be misrouted to the equity fetch")
    shaped = _prediction_candles([(T0, 0.3), (T0 + STEP, 0.5)], (T0 + 2 * STEP, 1.0))
    check(len(shaped) == 3 and shaped[0]["c"] == 0.3
          and shaped[0]["h"] == shaped[0]["l"] == 0.3,   # flat bars
          "prob history must shape into flat close-only bars")
    check(shaped[-1].get("res") and shaped[-1]["c"] == 1.0,
          "a resolved contract must append a settled (res) bar at the outcome")
    check(_prediction_candles([(T0, 0.3)], None)[-1].get("res") is None,
          "an open contract must not carry a settled bar")

    # the seed preset is a valid resolution strategy
    from core.presets import PRED_MREV
    check(parse(PRED_MREV).get("market") == "prediction",
          "PRED_MREV preset must parse as a prediction strategy")

    if ok:
        print("PASS: prediction settles to 1/0 on the right contract side, all "
              "four corners correct, flat-stake sizing, early exit at live prob, "
              "close-only capability enforced.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
