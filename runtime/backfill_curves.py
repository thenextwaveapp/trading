"""Backfill the mark-to-market equity curve for deployed bots.

The live curve the web draws comes from pf_bot_marks. Older marks stored only
*realized* equity (flat between closes). This rebuilds each deployed bot's marks
as the canonical mark-to-market curve — realized P&L plus open positions marked
to the real candle price through each hold — using core.equity.mtm_curve over
real Binance candles. Engine computes, DB stores, web renders. One source.

    DRY=1 python3 -m runtime.backfill_curves [botname]   # compute + print
          python3 -m runtime.backfill_curves [botname]   # rewrite marks
"""
import os
import sys
import json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.env  # noqa: F401
from core.equity import mtm_curve
from core.service import fetch_candles
from . import pf_db

DRY = bool(os.environ.get("DRY"))
START = 10000.0
URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def _coin_map():
    rows = pf_db.get("pf_coins", "select=symbol,binance_symbol")
    return {r["symbol"]: r["binance_symbol"] for r in rows}


def _deployed_bots(name=None):
    q = "stage=eq.deployed&select=id,name"
    if name:
        q += f"&name=eq.{name}"
    return pf_db.get("pf_bots", q)


def _trades(bot_id):
    return pf_db.get(
        "pf_bot_trades",
        f"bot_id=eq.{bot_id}&select=t_sig,exit_t,ticker,side,entry,notional,pnl,net"
        "&order=exit_t.asc")


def _prices_for(trades, cmap):
    prices = {}
    for tk in {t["ticker"] for t in trades}:
        tks = [t for t in trades if t["ticker"] == tk]
        start = min(int(t["t_sig"]) for t in tks)
        end = max(int(t["exit_t"]) for t in tks)
        sym = cmap.get(tk, f"{tk}USDT")
        try:
            cs = fetch_candles(sym, interval="15m", limit=1500, start=start, end=end)
        except Exception as e:
            print(f"    ! {tk} ({sym}) candles failed: {e}")
            cs = []
        prices[tk] = [[c["t"], c["c"]] for c in cs]
    return prices


def _curve_for(bot, cmap):
    trades = _trades(bot["id"])
    if not trades:
        return [], 0
    prices = _prices_for(trades, cmap)
    norm = [{"entry_t": t["t_sig"], "exit_t": t["exit_t"], "ticker": t["ticker"],
             "side": t["side"], "entry": t["entry"], "notional": t["notional"],
             "pnl": t["pnl"] if t["pnl"] is not None else t.get("net")}
            for t in trades]
    return mtm_curve(norm, prices, START), len(trades)


def _latest_mark(bot_id):
    rows = pf_db.get("pf_bot_marks",
                     f"bot_id=eq.{bot_id}&select=*&order=t.desc&limit=1")
    return rows[0] if rows else None


def _delete_marks(bot_id):
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_bot_marks?bot_id=eq.{bot_id}", method="DELETE",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


def _insert_marks(rows):
    req = urllib.request.Request(
        f"{URL}/rest/v1/pf_bot_marks", data=json.dumps(rows).encode(), method="POST",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=60).read()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    name = argv[0] if argv else None
    cmap = _coin_map()
    bots = _deployed_bots(name)
    print(f"{len(bots)} deployed bot(s){' (filtered)' if name else ''}")
    for b in bots:
        curve, n = _curve_for(b, cmap)
        if not curve:
            print(f"[{b['name']}] {n} trades -> no curve (no candles/trades)")
            continue
        lo, hi = curve[0][1], curve[-1][1]
        peak = max(p[1] for p in curve)
        trough = min(p[1] for p in curve)
        print(f"[{b['name']}] {n} trades -> {len(curve)} pts · "
              f"start {lo:.0f} end {hi:.2f} · range {trough:.0f}–{peak:.0f}")
        if DRY:
            continue
        # The curve is derived purely from the trade ledger (one source), so it
        # is internally consistent. Carry only the open positions from the live
        # tip (for the open-trades panel) — NOT its equity, which may be a
        # divergent value from the old double-run.
        tip = _latest_mark(b["id"])
        marks = [{"bot_id": b["id"], "t": int(t), "equity": round(eq, 2),
                  "ret": eq / START - 1, "closed": n} for t, eq in curve]
        if tip and tip.get("open_json"):
            end_eq = curve[-1][1]
            marks.append({"bot_id": b["id"], "t": int(tip["t"]),
                          "equity": round(end_eq, 2), "ret": end_eq / START - 1,
                          "closed": n, "open_json": tip["open_json"],
                          "win": tip.get("win")})
        _delete_marks(b["id"])
        for i in range(0, len(marks), 500):
            _insert_marks(marks[i:i + 500])
    print("DRY — no writes." if DRY else "rebuilt marks.")


if __name__ == "__main__":
    main()
