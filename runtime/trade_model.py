"""Shared trade model + candle fetch for the live fleet.

The fee/sizing numbers come from core.backtest.DEFAULTS so live/paper and the
backtester never drift apart. Concurrency + kill-switch are runtime-only
operational params with no backtest equivalent. `klines` is the candle fetch:
Binance USDT-M futures, with non-USDT symbols routed to Yahoo via core.service.

This is the neutral home for the pieces the live fleet (spec_runtime,
fleet.runner, server.app) shares; it carries no strategy logic.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

from core.backtest import DEFAULTS as _MODEL

M15 = 900_000

# Trade model — fees, sizing, starting equity. Single source of truth is
# core.backtest.DEFAULTS, so live/paper and the backtester never drift apart.
TAKER = _MODEL["taker"]
SLIP = _MODEL["slip"]
RISK = _MODEL["risk"]
NOTIONAL_CAP = _MODEL["notional_cap"]
START_EQUITY = _MODEL["start_equity"]

# Live-fleet operational params (no backtest equivalent): concurrency + kill-switch.
MAX_CONC = 6
KILL_DD = -0.05
KILL_LOOKBACK = 7 * 86_400_000
KILL_PAUSE = 3 * 86_400_000

API = "https://fapi.binance.com/fapi/v1/klines"


def log(msg):
    print(f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {msg}",
          flush=True)


def klines(symbol, limit=25, start=None, interval="15m"):
    if not str(symbol).upper().endswith("USDT"):
        from core.service import _fetch_equity
        rows = _fetch_equity(symbol, interval=interval, limit=limit, start=start)
        return rows if rows else None
    url = f"{API}?symbol={symbol}&interval={interval}&limit={limit}"
    if start is not None:
        url += f"&startTime={start}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                rows = json.loads(r.read())
            now = int(time.time() * 1000)
            return [dict(t=int(r[0]), o=float(r[1]), h=float(r[2]), l=float(r[3]),
                         c=float(r[4]), v=float(r[5]))
                    for r in rows if int(r[6]) <= now]  # closed candles only
        except Exception as e:
            if attempt == 2:
                log(f"WARN {symbol}: fetch failed ({e})")
                return None
            time.sleep(2 * (attempt + 1))
