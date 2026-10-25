"""Weather — performance by Bitcoin trend and market volatility.

The Build flow's Weather step answers one question: when does this bot make
money? We take the bot's own backtest ledger and bucket every trade by the
market state at entry:

  trend       BTC's trailing 24h return: rising (> +1%), falling (< -1%),
              or flat in between.
  volatility  BTC's realized 15m volatility over the trailing 24h, split into
              low / normal / high terciles across the backtest window.

Trades are pooled inside each of the nine cells; `return_per_trade` is the
mean net return (in percent, after costs) of the trades in that cell. Cells
with no trades stay in the result with `return_per_trade=None` so the UI can
draw the full grid. `is_current` marks the cell matching the latest closed
BTC candle.

This is a reporting instrument, not a signal: nothing here feeds entries or
changes the backtest. The selection of cells is stored on `pf_bots` as the
bot's regime gate.
"""
import math

M15 = 900_000
VOL_WINDOW = 96          # 24h of 15m bars
TREND_BAND = 0.01        # +-1% 24h return is "flat"

VOLS = ("low", "normal", "high")
TRENDS = ("falling", "flat", "rising")


def _prefix(xs):
    out = [0.0]
    for x in xs:
        out.append(out[-1] + x)
    return out


def _realized_vol(closes):
    """Population stdev of 15m log returns over the trailing 24h, per bar."""
    n = len(closes)
    r = [0.0] * n
    for i in range(1, n):
        if closes[i] > 0 and closes[i - 1] > 0:
            r[i] = math.log(closes[i] / closes[i - 1])
    p = _prefix(r)
    p2 = _prefix([x * x for x in r])
    out = [None] * n
    for i in range(VOL_WINDOW, n):
        lo = i - VOL_WINDOW + 1
        m = (p[i + 1] - p[lo]) / VOL_WINDOW
        v = max((p2[i + 1] - p2[lo]) / VOL_WINDOW - m * m, 0.0)
        out[i] = math.sqrt(v)
    return out


def _terciles(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None, None
    lo = vals[int(0.33 * (len(vals) - 1))]
    hi = vals[int(0.67 * (len(vals) - 1))]
    if lo == hi:
        return None, None
    return lo, hi


def _vol_cat(v, lo, hi):
    if v is None or lo is None:
        return "normal"
    if v <= lo:
        return "low"
    if v >= hi:
        return "high"
    return "normal"


def _trend_cat(closes, i):
    if i < VOL_WINDOW:
        return "flat"
    r = closes[i] / closes[i - VOL_WINDOW] - 1
    if r > TREND_BAND:
        return "rising"
    if r < -TREND_BAND:
        return "falling"
    return "flat"


def _bar_index(t, ts):
    """Index of the last BTC bar at or before time ts (ms)."""
    lo, hi = 0, len(t) - 1
    if not t:
        return -1
    if ts < t[0]:
        return -1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if t[mid] <= ts:
            lo = mid
        else:
            hi = mid - 1
    return lo


def conditions_breakdown(trades, candles_by_ticker):
    """-> [9 cells] ordered low/normal/high x falling/flat/rising.

    `trades` is the engine ledger (each trade carries `t_sig`, `net` as a
    fraction). `candles_by_ticker` must contain BTC for the regime measure;
    without it we return no cells rather than inventing a market state.
    """
    btc = candles_by_ticker.get("BTC")
    if not btc:
        return []

    t = [k["t"] for k in btc]
    c = [k["c"] for k in btc]
    rv = _realized_vol(c)
    lo, hi = _terciles(rv)

    cells = {(v, tr): {"volatility": v, "btc_trend": tr,
                       "return_per_trade": None, "trades": 0,
                       "is_current": False}
             for v in VOLS for tr in TRENDS}

    for trade in trades:
        entry = trade.get("t_sig")
        if entry is None:
            continue
        i = _bar_index(t, entry - M15)      # the signal bar, last closed candle
        if i < 0:
            continue
        v = _vol_cat(rv[i], lo, hi)
        tr = _trend_cat(c, i)
        cell = cells[(v, tr)]
        cell["_sum"] = cell.get("_sum", 0.0) + float(trade.get("net") or 0.0)
        cell["trades"] += 1

    now = len(c) - 1
    if now >= 0:
        cur = ( _vol_cat(rv[now], lo, hi), _trend_cat(c, now) )
        if cur in cells:
            cells[cur]["is_current"] = True

    out = []
    for v in VOLS:
        for tr in TRENDS:
            cell = cells[(v, tr)]
            n = cell["trades"]
            cell["return_per_trade"] = round(cell["_sum"] / n * 100, 4) if n else None
            # Persist the training-window terciles with every cell so the live
            # fleet can classify today's regime on the same scale.
            cell["vol_lo"] = lo
            cell["vol_hi"] = hi
            cell.pop("_sum", None)
            out.append(cell)
    return out


def cell_at(candles, at_ms=None, vol_lo=None, vol_hi=None):
    """The (volatility, trend) cell at `at_ms` (default: latest bar).

    `vol_lo` / `vol_hi` must be the terciles from the training window (stored
    with `pf_bots.condition_filter`); without them we cannot reproduce the
    classification and return None rather than guessing.
    """
    if not candles or vol_lo is None or vol_hi is None:
        return None
    t = [k["t"] for k in candles]
    c = [k["c"] for k in candles]
    i = _bar_index(t, at_ms - M15) if at_ms is not None else len(c) - 1
    if i < 0:
        return None
    rv = _realized_vol(c)
    return (_vol_cat(rv[i], vol_lo, vol_hi), _trend_cat(c, i))
