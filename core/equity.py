"""Mark-to-market equity curve — the account traced bar-by-bar.

Realized P&L steps at each trade's exit; while a position is open it is marked
to the bar price, so the equity line follows the underlying through the hold and
settles at close (instead of a flat line that only jumps on exit).

This is the canonical equity series: the engine computes it and stores it, the
web only renders it. One source of truth.
"""
import bisect


def _sign(side):
    return 1 if side in (1, "1", "long", "LONG") else -1


def mtm_curve(trades, prices_by_ticker, start_equity=10000.0):
    """Dense equity curve over the trades' span.

    trades: [{entry_t, exit_t, ticker, side, entry, notional, pnl}] (ms times).
    prices_by_ticker: {ticker: [[t_ms, close], ...]} ascending by t.
    Returns [[t_ms, equity], ...]: realized P&L at each bar plus the unrealized
    P&L of every position open at that bar — flat between trades, wiggling with
    price through each hold.
    """
    live = [t for t in trades
            if t.get("entry_t") is not None and t.get("exit_t") is not None]
    if not live:
        return []
    lo = min(int(t["entry_t"]) for t in live)
    hi = max(int(t["exit_t"]) for t in live)

    # bar grid: every candle time across the span (union over tickers)
    times = sorted({tt for rows in prices_by_ticker.values()
                    for tt, _px in rows if lo <= tt <= hi})
    if not times:
        return []

    # step-price lookup: the last close at or before t, per ticker
    idx = {tk: ([r[0] for r in rows], [r[1] for r in rows])
           for tk, rows in prices_by_ticker.items()}

    def price_at(tk, t):
        arr = idx.get(tk)
        if not arr or not arr[0]:
            return None
        i = bisect.bisect_right(arr[0], t) - 1
        return arr[1][i] if i >= 0 else None

    exits = sorted((int(t["exit_t"]), float(t.get("pnl") or 0.0)) for t in live)
    exit_ts = [e[0] for e in exits]
    exit_cum = []
    run = 0.0
    for _t, p in exits:
        run += p
        exit_cum.append(run)

    def realized_at(t):
        # cumulative pnl of trades already exited by time t
        k = bisect.bisect_right(exit_ts, t)
        return start_equity + (exit_cum[k - 1] if k else 0.0)

    curve = []
    for t in times:
        eq = realized_at(t)
        for tr in live:
            if int(tr["entry_t"]) <= t < int(tr["exit_t"]):
                px = price_at(tr["ticker"], t)
                entry = float(tr.get("entry") or 0)
                if px and entry:
                    eq += float(tr.get("notional") or 0) * _sign(tr.get("side")) * (px / entry - 1)
        curve.append([t, round(eq, 2)])

    if curve[0][0] > lo:
        curve.insert(0, [lo, round(start_equity, 2)])
    return curve
