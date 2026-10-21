"""Universe resolution is rule-based: a universe resolves from market data, not
a frozen list. Proves resolve() against the real local bn_coverage instruments —
a threshold rule, a top-N rule, and the degenerate list case.

Run:  python3 -m core.selftest_universe
"""
import sys

from core.universe import resolve
from core.marketdata import from_bn_coverage


def check(label, cond):
    print(f"  [{'OK ' if cond else 'FAIL'}] {label}")
    return cond


def main():
    ok = True
    inst = from_bn_coverage()
    ok &= check(f"loaded instruments ({len(inst)})", len(inst) > 100)
    ok &= check("deduped by binance_symbol",
                len({i["binance_symbol"] for i in inst}) == len(inst))

    # threshold rule: established perps = >=180d of history
    est = resolve({"rule": {"metric": "history_days", "op": "ge",
                            "value": 180}}, inst)
    ok &= check(f"rule >=180d resolves a real set ({len(est)})",
                30 <= len(est) <= 60)
    ok &= check("includes the obvious majors",
                all(t in est for t in ("BTC", "ETH", "SOL")))
    ok &= check("1000PEPE appears once (dedup held)",
                list(est.values()).count("1000PEPEUSDT") <= 1)

    # top-N rule by history depth
    top20 = resolve({"rule": {"sort": "history_bars", "top": 20}}, inst)
    ok &= check("top-20 returns exactly 20", len(top20) == 20)
    ok &= check("top-20 ⊂ established", set(top20) <= set(est))

    # degenerate list universe
    lst = resolve({"list": ["BTC", "ETH"]}, inst)
    ok &= check("list resolves to its tickers",
                lst == {"BTC": "BTCUSDT", "ETH": "ETHUSDT"})

    # a thin coin that should NOT make the established cut
    thin = [i["ticker"] for i in inst if i["metrics"]["history_days"] < 30]
    ok &= check("thin coins excluded from >=180d rule",
                thin and all(t not in est for t in thin))

    print("\nPASS: universes resolve from market data (rule + list)."
          if ok else "\nFAIL: see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
