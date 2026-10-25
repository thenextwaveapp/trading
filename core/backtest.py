"""Backtest engine — replay a strategy over one instrument's history.

Wraps the shared evaluator (entry_signal) in a historical loop:
  - entries via entry_signal
  - build the position's stop from the strategy's exit rule
  - resolve the exit (stop / take-profit / trailing / time)
  - one position per instrument (a new signal while open is skipped)

Returns the trade ledger + summary stats; `net_pct_per_trade` is the `bt`
number the dashboard compares against.

Entries come from entry_signal, exits from exit_trade. Fees and slippage are
always applied. No look-ahead: a trade's exit only uses candles at or after
its signal bar. Exit modes implemented: `hh` (stop at the signal-window high
+ buffer), `none` (no stop), `dstop` (disaster stop), `sig` (momo
signal-window stop), take-profit (intrabar or close-cross), short trailing
stop.
"""
from .evaluator import entry_signal, M15

DEFAULTS = {
    "taker": 0.00045,
    "slip": 0.0005,
    "risk": 0.0075,
    "notional_cap": 0.20,
    "start_equity": 10_000.0,
}


def build_position(strategy, candles, i, sig):
    """Construct the position (entry, side, hold, stop level, tp, trailing)
    from the strategy's exit rule and the firing signal at bar i."""
    ex = strategy.get("exit", {})
    side = 1 if strategy["side"] == "long" else -1
    entry = sig["entry"]
    stopspec = ex.get("stop", {"mode": "none", "param": 0.0})
    mode, param = stopspec.get("mode", "none"), stopspec.get("param", 0.0)

    if mode == "hh":                      # stop at the signal-window high
        w = stopspec.get("window", 16)
        hh = max(c["h"] for c in candles[i - w:i + 1])
        level = hh * (1 + param)
    elif mode == "dstop":                 # disaster stop below entry
        level = entry * (1 - param)
    elif mode == "none":                  # no stop (level 0 never hit)
        level = 0.0
    elif mode == "sig":                   # momo: signal-window computed stop
        w = stopspec.get("window", 16)    # max(window low, midpoint) - buffer
        buf = stopspec.get("param", 0.001)
        seg = candles[i - w + 1:i + 1]
        ll = min(c["l"] for c in seg)
        o0 = seg[0]["o"]
        level = max(ll, (o0 + candles[i]["c"]) / 2) * (1 - buf)
    else:
        level = stopspec.get("level", 0.0)

    pos = {"entry": entry, "hold": ex.get("time_bars"), "side": side,
           "stop": level, "t_sig": sig["t_sig"]}

    tp = ex.get("take_profit")
    if tp:
        pos["tp"] = entry * (1 + tp) if side > 0 else entry * (1 - tp)
        if ex.get("tp_close"):
            pos["tp_close"] = True
    tr = ex.get("trailing")
    if tr and side < 0:
        pos["trail_k"], pos["natr"] = tr.get("k"), tr.get("natr")
    return pos


def exit_trade(pos, candles, taker, slip):
    """Resolve a position to (net, exit_t, kind). Order: stop breach, then
    take-profit, then (short) trailing ratchet, then time exit at `hold`. net
    is the side-signed return minus both-leg taker fees + slippage. None if
    candles run out first."""
    entry, hold, side = pos["entry"], pos["hold"], pos.get("side", -1)
    level, low_min = pos["stop"], entry
    trail_k, natr, tp = pos.get("trail_k"), pos.get("natr"), pos.get("tp")
    fee = 2 * taker + slip
    post = [k for k in candles if k["t"] >= pos["t_sig"]][:hold]
    for n, k in enumerate(post, 1):
        # level 0 = "no stop" sentinel (never breached, either side), else a
        # short with stop mode "none" would instant-stop at level 0.
        if level and ((k["h"] > level) if side < 0 else (k["l"] < level)):
            return side * (level / entry - 1) - fee, k["t"] + M15, "sl"
        if tp and pos.get("tp_close"):
            if (k["c"] <= tp) if side < 0 else (k["c"] >= tp):
                return side * (k["c"] / entry - 1) - fee, k["t"] + M15, "tp"
        elif tp and ((k["l"] <= tp) if side < 0 else (k["h"] >= tp)):
            return side * (tp / entry - 1) - fee, k["t"] + M15, "tp"
        if side < 0 and trail_k and natr:
            low_min = min(low_min, k["l"])
            level = min(level, low_min * (1 + trail_k * natr))
        if n == hold:
            return side * (k["c"] / entry - 1) - fee, k["t"] + M15, "time"
    return None


def summarize(trades, cfg):
    """Pooled expectancy + a risk-sized compounded equity curve."""
    n = len(trades)
    if not n:
        return {"n": 0, "net_pct_per_trade": 0.0, "win_rate": 0.0,
                "total_net_pct": 0.0, "final_equity": cfg["start_equity"],
                "max_drawdown": 0.0, "kinds": {}, "equity_curve": []}
    nets = [t["net"] for t in trades]
    kinds = {}
    for t in trades:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    # compound a risk-sized equity curve ordered by exit time (pooled
    # multi-instrument runs compound in the sequence trades closed). Start at
    # the earliest signal across instruments so the series is chronological
    # even when the first trade in the pooled list belongs to another ticker.
    eq = cfg["start_equity"]
    peak = eq
    max_dd = 0.0
    curve = [[min(t["t_sig"] for t in trades), round(eq, 2)]]
    for t in sorted(trades, key=lambda x: x["exit_t"]):
        sl_dist = t["stop"] / t["entry"] - 1
        notional = min(cfg["risk"] * eq / max(abs(sl_dist), 0.005),
                       cfg["notional_cap"] * eq)
        eq += notional * t["net"]
        peak = max(peak, eq)
        max_dd = min(max_dd, eq / peak - 1)
        if curve[-1][0] == t["exit_t"]:
            curve[-1][1] = round(eq, 2)
        else:
            curve.append([t["exit_t"], round(eq, 2)])
    return {
        "n": n,
        "net_pct_per_trade": sum(nets) / n * 100,
        "win_rate": sum(1 for x in nets if x > 0) / n,
        "total_net_pct": sum(nets) * 100,
        "final_equity": round(eq, 2),
        "max_drawdown": round(max_dd, 4),
        "kinds": kinds,
        "equity_curve": curve,
    }


def backtest(strategy, candles, cfg=None, start=0, entry_delay=0):
    """Run `strategy` over one instrument's candle list. Returns
    {trades, stats}. `start` skips leading bars; entry_signal refuses to fire
    before the strategy's lookback is satisfied, so start=0 fires as soon as a
    signal is valid.

    `entry_delay` fills `d` bars after the signal (enter at candles[i+d]'s
    close instead of the signal close). The stop reference still comes from
    the signal bar; only the fill moves."""
    cfg = {**DEFAULTS, **(cfg or {})}
    taker, slip = cfg["taker"], cfg["slip"]
    trades, cache, open_until = [], {}, -1
    for i in range(start, len(candles)):
        sig = entry_signal(strategy, candles, i, cache)
        if not sig or sig["t_sig"] < open_until:
            continue
        fi = i + entry_delay
        if fi >= len(candles):
            continue
        fsig = sig if entry_delay == 0 else {
            **sig, "entry": candles[fi]["c"], "t_sig": candles[fi]["t"] + M15}
        pos = build_position(strategy, candles, i, fsig)  # i -> stop window
        ex = exit_trade(pos, candles, taker, slip)
        if ex is None:
            continue
        net, exit_t, kind = ex
        trades.append({"t_sig": fsig["t_sig"], "entry": pos["entry"],
                       "stop": pos["stop"], "exit_t": exit_t, "kind": kind,
                       "net": net})
        open_until = exit_t
    return {"trades": trades, "stats": summarize(trades, cfg)}


def backtest_universe(strategy, candles_by_ticker, cfg=None, start=0,
                      entry_delay=0):
    """Run `strategy` across many instruments and pool the trades. The
    reported expectancy is over the pooled ledger."""
    cfg = {**DEFAULTS, **(cfg or {})}
    all_trades = []
    for tk, candles in candles_by_ticker.items():
        r = backtest(strategy, candles, cfg, start=start,
                     entry_delay=entry_delay)
        for t in r["trades"]:
            all_trades.append({**t, "ticker": tk})
    return {"trades": all_trades, "stats": summarize(all_trades, cfg)}
