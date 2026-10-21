"""core.db.universe_symbols routes both universe kinds through one resolver: a
rule-universe resolves against the live tradeable set (provider), a list- (incl.
user-picked) universe from its stored coins. Stubs the Supabase reads + provider
so it runs offline.

Run:  python3 -m core.selftest_db_universe
"""
import sys

import core.db as db


def check(label, cond):
    print(f"  [{'OK ' if cond else 'FAIL'}] {label}")
    return cond


UNIS = {
    "eq.topvol": {"id": "u1", "definition":
                  {"rule": {"metric": "history_days", "op": "ge", "value": 180}}},
    "eq.mylist": {"id": "u2", "definition": None},   # a user's hand-picked list
}
COINS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "NEW": "NEWUSDT"}


def fake_get(path, params):
    if path == "pf_universes":
        return [UNIS[params["slug"]]] if params["slug"] in UNIS else []
    if path == "pf_universe_coins":
        return [{"coin_symbol": "BTC"}, {"coin_symbol": "ETH"}]   # mylist's coins
    if path == "pf_coins":
        want = params["symbol"].removeprefix("in.(").rstrip(")").split(",")
        return [{"symbol": s, "binance_symbol": COINS[s]}
                for s in want if s in COINS]
    return []


def main():
    ok = True
    db.URL, db.KEY = "http://stub", "k"          # make enabled() true
    db._get = fake_get
    db.set_provider(lambda: [
        {"ticker": "BTC", "binance_symbol": "BTCUSDT",
         "metrics": {"history_days": 900}},
        {"ticker": "NEW", "binance_symbol": "NEWUSDT",
         "metrics": {"history_days": 5}},      # too new -> filtered by the rule
    ])

    db._cache.clear()
    rule = db.universe_symbols("topvol")
    ok &= check("rule-universe resolves via provider (threshold)",
                rule == {"BTC": "BTCUSDT"})

    db._cache.clear()
    lst = db.universe_symbols("mylist")
    ok &= check("list-universe resolves from stored coins",
                lst == {"BTC": "BTCUSDT", "ETH": "ETHUSDT"})

    print("\nPASS: universe_symbols routes rule + list through one resolver."
          if ok else "\nFAIL: see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
