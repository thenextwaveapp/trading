"""Market-data providers — the live tradeable set + per-instrument metrics
that rule-universes resolve against. Each provider returns the same shape:

    [{"ticker": str, "binance_symbol": str, "metrics": {name: number, ...}}, ...]

so a universe rule (universe.resolve) is provider-agnostic.
 - LIVE: Binance exchangeInfo for the perp list + the 24h ticker for volume ->
   metric "volume_24h".
 - OFFLINE: from_bn_coverage() reads the local bn/ pull; metric "history_days"
   (a liquidity/longevity proxy) since it only knows each symbol's history.
"""
import csv
import json
import os
import urllib.request

_FAPI = "https://fapi.binance.com/fapi/v1"


def from_binance(timeout=20):
    """LIVE instruments: every tradeable USDT perpetual from Binance
    exchangeInfo, with metric volume_24h (quote volume from the 24h ticker) —
    the liquidity a rule-universe like 'top 100 by volume' ranks on. Raises on
    a failed fetch (caller falls back)."""
    def _get(path):
        with urllib.request.urlopen(f"{_FAPI}/{path}", timeout=timeout) as r:
            return json.loads(r.read())
    info = _get("exchangeInfo")
    perps = {s["symbol"]: s for s in info["symbols"]
             if s.get("contractType") == "PERPETUAL"
             and s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"}
    vol = {t["symbol"]: float(t.get("quoteVolume", 0))
           for t in _get("ticker/24hr") if t["symbol"] in perps}
    out = []
    for sym, meta in perps.items():
        base = meta.get("baseAsset") or sym[:-4]
        out.append({"ticker": base, "binance_symbol": sym,
                    "metrics": {"volume_24h": vol.get(sym, 0.0)}})
    return out


def from_bn_coverage(path=None):
    """Instruments from lab/bn/bn_coverage.csv, deduped by binance_symbol (keep
    the deepest-history ticker when the same contract appears under two names,
    e.g. kPEPE / PEPE -> 1000PEPEUSDT). Metric: history_days (15m bars / 96).

    Offline/dev helper only — production resolves universes from the DB."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "..", "lab", "bn",
                            "bn_coverage.csv")
    rows = sorted(csv.DictReader(open(path)),
                  key=lambda r: -int(r["c15m_kept"] or 0))
    out, seen = [], set()
    for r in rows:
        bs = r["symbol"]
        if bs in seen:
            continue
        seen.add(bs)
        bars = int(r["c15m_kept"] or 0)
        out.append({"ticker": r["ticker"], "binance_symbol": bs,
                    "metrics": {"history_days": bars / 96, "history_bars": bars}})
    return out
