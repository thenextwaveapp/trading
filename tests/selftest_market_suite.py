"""Per-market evaluation suite — a market is judged by its own physics.

The engine accepts equity/fx/futures markets, but the evaluation layer used to
be hardcoded crypto: Binance perp fees for everyone, and a volume liveness guard
that killed volume-less markets outright. The suite now lives on the Market
adapter. This pins:

  - cost is per-market (crypto taker != equity commission != fx spread), and an
    identical strategy nets the fee difference between markets;
  - crypto is unchanged (its market cost equals the historical DEFAULTS);
  - a volume-less market (fx_spot) can actually fire signals.

Run: python3 -m tests.selftest_market_suite
"""
from core.backtest import DEFAULTS, backtest, market_cost
from core.conditions import conditions_breakdown
from core.evaluator import entry_signal
from core.markets import MARKETS
from core.strategy import parse
from runtime.spec_runtime import new_state, run_spec_signals

M15 = 900_000
T0 = 1_700_000_000_000
ENTRY = {"logic": "AND", "children": [
    {"left": {"ind": "close"}, "op": "gt", "right": 0}]}


def spec(market):
    return parse({"name": "m", "side": "long", "market": market,
                  "timeframe": "15m", "entry": ENTRY,
                  "exit": {"time_bars": 6, "stop": {"mode": "none"}}})


def main():
    ok = True

    def check(c, msg):
        nonlocal ok
        if not c:
            print("FAIL:", msg)
            ok = False

    # crypto cost is unchanged — equals the historical crypto DEFAULTS
    cp = market_cost(spec("crypto_perp"))
    check(cp["taker"] == DEFAULTS["taker"] and cp["slip"] == DEFAULTS["slip"],
          f"crypto_perp cost must equal the legacy DEFAULTS, got {cp}")

    # each market carries its own, distinct cost
    eq = market_cost(spec("equity"))
    fx = market_cost(spec("fx_spot"))
    check(eq != cp and fx != cp, "equity and fx must not use crypto costs")
    check(MARKETS["equity"].regime_benchmark == "SPY"
          and MARKETS["crypto_perp"].regime_benchmark == "BTC",
          "each market must declare its own regime benchmark")

    # an unknown market falls back to DEFAULTS (so market-less tests are stable)
    check(market_cost(parse({"name": "x", "side": "long", "timeframe": "15m",
                             "entry": ENTRY, "exit": {"time_bars": 6}})) == {},
          "a market-less strategy must carry no market cost (falls back)")

    # identical strategy + candles -> net differs by exactly the round-trip fee
    c = [{"t": T0 + i * M15, "o": 100.0, "h": 100.5, "l": 99.5,
          "c": 100.0 + (i % 7) * 0.3, "v": 10.0} for i in range(60)]
    npt_cp = backtest(spec("crypto_perp"), c)["stats"]["net_pct_per_trade"]
    npt_eq = backtest(spec("equity"), c)["stats"]["net_pct_per_trade"]
    fee_cp = 2 * cp["taker"] + cp["slip"]
    fee_eq = 2 * eq["taker"] + eq["slip"]
    check(abs((npt_eq - npt_cp) - (fee_cp - fee_eq) * 100) < 1e-9,
          f"equity net should beat crypto by the fee delta, got "
          f"{npt_eq - npt_cp} vs {(fee_cp - fee_eq) * 100}")

    # fx_spot has no volume column; its bars (v=0) must still be 'alive'
    fx_c = [{"t": T0 + i * M15, "o": 1.10, "h": 1.101, "l": 1.099,
             "c": 1.10 + (i % 5) * 0.001, "v": 0.0} for i in range(40)]
    fired = sum(1 for i in range(len(fx_c))
                if entry_signal(spec("fx_spot"), fx_c, i, {}))
    check(fired > 0, "fx_spot (no volume) must be able to fire signals")
    # and the volume guard still bites where volume IS expected (crypto, v=0)
    dead = sum(1 for i in range(len(fx_c))
               if entry_signal(spec("crypto_perp"), fx_c, i, {}))
    check(dead == 0, "a volume market with zero volume must still read as dead")

    # Weather/regime is measured on the market's benchmark, not hardcoded BTC
    bench = [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
              "c": 100.0 + (i % 20) * 0.5, "v": 10.0} for i in range(300)]
    tr = [{"t_sig": T0 + i * M15, "net": 0.01} for i in range(100, 200)]
    check(len(conditions_breakdown(tr, {"BTC": bench}, market="crypto_perp")) == 9,
          "crypto Weather resolves BTC from the candle set")
    check(len(conditions_breakdown(tr, {"AAPL": bench}, market="equity")) == 0,
          "equity Weather is empty without its benchmark — no faking BTC")
    check(len(conditions_breakdown(tr, {"AAPL": bench}, benchmark=bench,
                                   market="equity")) == 9,
          "equity Weather works when its benchmark (SPY) is supplied")
    check(len(conditions_breakdown(tr, {"EURUSD": bench}, market="fx_spot")) == 0,
          "a market with no regime benchmark has no Weather at all")

    # LIVE side: a position opened by the live engine is priced by its market's
    # cost, so the live exit matches the backtest (eval suite holds end-to-end).
    live_c = [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
               "c": 100.0, "v": 10.0} for i in range(20)]
    nofetch = (lambda *a, **k: [])
    for mk, want_taker in (("crypto_perp", DEFAULTS["taker"]), ("equity", 0.0001)):
        sp = {"name": "x", "side": "long", "market": mk, "timeframe": "15m",
              "entry": ENTRY, "exit": {"time_bars": 4, "stop": {"mode": "none"}}}
        st = new_state()
        run_spec_signals("x", sp, st, {"AAA": "AAA"}, {"AAA": live_c},
                         notes=[], fetch=nofetch, resolve=lambda _t: None)
        got = st["positions"][0].get("taker") if st["positions"] else None
        check(got is not None and abs(got - want_taker) < 1e-12,
              f"{mk} live position must carry {mk} cost, got taker {got}")

    if ok:
        print("PASS: cost, regime benchmark, and liveness are per-market; "
              "crypto unchanged, equity repriced, fx fires, Weather uses the "
              "right benchmark, live positions carry the market's cost.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
