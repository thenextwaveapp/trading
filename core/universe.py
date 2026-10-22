"""Universe resolution — a universe is the set of instruments a strategy may
trade, resolved from market DATA, not a frozen hand-picked list.

A universe DEFINITION is one of:
    {"list": ["BTC", "ETH", ...]}                      explicit tickers
    {"rule": {"metric": "volume_24h", "op": "ge",      a threshold predicate
              "value": 1e8}}                           over a market metric
    {"rule": {"sort": "volume_24h", "top": 100}}       top-N by a metric
(threshold and sort/top compose: "the 100 highest-volume perps over $X".)

It resolves against INSTRUMENTS — the current tradeable set, each carrying its
metrics — supplied by a market-data provider (see marketdata.py). A frozen list
is simply the degenerate rule; same concept, same role in a spec. Swap the
provider (Binance perps today, equities later) or refresh it (volume moved) and
every rule-universe re-resolves against current reality — nothing downstream
changes. That is why `fleet-60` stops being special: it's one list among rules.
"""

_OPS = {"ge": lambda a, b: a >= b, "le": lambda a, b: a <= b,
        "gt": lambda a, b: a > b, "lt": lambda a, b: a < b}


def resolve(definition, instruments):
    """(definition, [{ticker, binance_symbol, metrics:{}}]) -> {ticker: binance_symbol}.

    Deterministic: same definition + same instruments -> same set. The order of
    the returned dict follows the sort (or instrument order for lists/thresholds)."""
    if "list" in definition:
        want = set(definition["list"])
        return {i["ticker"]: i["binance_symbol"]
                for i in instruments if i["ticker"] in want}

    rule = definition["rule"]
    rows = list(instruments)
    if rule.get("metric") and "op" in rule and "value" in rule:
        op = _OPS[rule["op"]]
        rows = [i for i in rows
                if op(i["metrics"].get(rule["metric"], 0), rule["value"])]
    if rule.get("sort"):
        rows.sort(key=lambda i: i["metrics"].get(rule["sort"], 0),
                  reverse=rule.get("desc", True))
    if rule.get("top"):
        rows = rows[:int(rule["top"])]
    return {i["ticker"]: i["binance_symbol"] for i in rows}
