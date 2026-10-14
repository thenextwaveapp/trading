#!/usr/bin/env python3
"""Regime view — the dials over time, and where we are today.

Three series, daily resolution, 2023-01 -> TODAY (cache + live top-up):
  1. PUMP dial  — trailing 30d mean 24h-forward return of pump events
                  (4h runup >= +12%), the short book's season. Negative =
                  pumps die = SHORT season.
  2. DUMP dial  — trailing 30d mean 24h-forward return of dump events
                  (24h return <= -10%), the long book's season. Positive =
                  dumps bounce = CAPIT-LONG season.
  3. BTC trend  — 4h EMA20 vs EMA50 (the live capit gate).

Causal: an event enters its dial only after its 24h outcome completes.
Computed from 1h candles (cache r60_*_1h + live Binance top-up), so values
are a close cousin of the fleet's 15m-based gate, not bit-identical.
Dial spec and machinery: regime.py (repo root) — this file is data + plots.

Usage: python3 regime_view.py          # writes + opens reports/regime_view.html
"""
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import regime

H = regime.H1
DAY = regime.DAY
API = "https://fapi.binance.com/fapi/v1/klines"


def live_topup(symbol, start):
    url = f"{API}?symbol={symbol}&interval=1h&limit=1000&startTime={start}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            rows = json.loads(r.read())
        now = int(time.time() * 1000)
        return [(int(x[0]), float(x[4])) for x in rows if int(x[6]) <= now]
    except Exception:
        return []


def load():
    c1 = pd.concat([pd.read_csv("backtest/r60_oos_1h.csv.gz"),
                    pd.read_csv("backtest/r60_candles_1h.csv.gz")])
    tickers = {}
    for tk, g in c1.groupby("ticker"):
        g = g.drop_duplicates("t").sort_values("t")
        tickers[tk] = dict(t=g["t"].to_numpy(np.int64),
                           c=g["c"].to_numpy(float),
                           sym=g["symbol"].iloc[0] if "symbol" in g else None)
    # symbol map from the fleet's universe builder (fallback: TK + USDT)
    syms = {tk: f"{tk[1:] if tk.startswith('k') else tk}USDT"
            if not tk.startswith("k") else f"1000{tk[1:]}USDT"
            for tk in tickers}
    last = max(d["t"][-1] for d in tickers.values())
    start = int(last - 2 * DAY)
    with ThreadPoolExecutor(max_workers=8) as ex:
        tops = dict(zip(tickers, ex.map(
            lambda tk: live_topup(syms[tk], start), tickers)))
    for tk, rows in tops.items():
        if not rows:
            continue
        d = tickers[tk]
        old_t, old_c = list(d["t"]), list(d["c"])
        have = set(old_t)
        for t, c in rows:
            if t not in have:
                old_t.append(t)
                old_c.append(c)
        order = np.argsort(old_t)
        d["t"] = np.array(old_t, np.int64)[order]
        d["c"] = np.array(old_c, float)[order]
    return tickers


def svg_strip(grid, vals, title, pos_label, neg_label, pos_color, neg_color,
              pct=True, width=1120, height=150):
    x0, x1, y_pad = 50, width - 10, 18
    t0, t1 = grid[0], grid[-1]
    v = np.array(vals, float)
    fin = np.isfinite(v)
    vmax = max(abs(np.nanmin(v)), abs(np.nanmax(v))) * 1.1 if fin.any() else 1
    def X(t): return x0 + (t - t0) / (t1 - t0) * (x1 - x0)
    def Y(val): return y_pad + (1 - (val + vmax) / (2 * vmax)) * (height - 2 * y_pad)
    parts = [f'<svg viewBox="0 0 {width} {height+28}" style="width:100%">']
    parts.append(f'<text x="{x0}" y="13" class="ttl">{title}</text>')
    # shaded sign bands
    seg_start, seg_sign = None, None
    for g in range(len(grid) + 1):
        s = None if g == len(grid) or not fin[g] else (v[g] > 0)
        if s != seg_sign:
            if seg_sign is not None and seg_start is not None:
                col = pos_color if seg_sign else neg_color
                parts.append(
                    f'<rect x="{X(grid[seg_start]):.1f}" y="{y_pad}" '
                    f'width="{X(grid[min(g, len(grid)-1)])-X(grid[seg_start]):.1f}" '
                    f'height="{height-2*y_pad}" fill="{col}" opacity="0.13"/>')
            seg_start, seg_sign = g if g < len(grid) else None, s
    parts.append(f'<line x1="{x0}" y1="{Y(0):.1f}" x2="{x1}" y2="{Y(0):.1f}" '
                 'stroke="#555" stroke-dasharray="3,3"/>')
    # year ticks
    for y in (2023, 2024, 2025, 2026):
        T = int(pd.Timestamp(f"{y}-01-01", tz="UTC").value // 10**6)
        if t0 <= T <= t1:
            parts.append(f'<line x1="{X(T):.1f}" y1="{y_pad}" x2="{X(T):.1f}" '
                         f'y2="{height-y_pad}" stroke="#333"/>')
            parts.append(f'<text x="{X(T)+4:.1f}" y="{height+12}" '
                         f'class="ax">{y}</text>')
    # the line
    pts, run = [], []
    for g in range(len(grid)):
        if fin[g]:
            run.append(f"{X(grid[g]):.1f},{Y(v[g]):.1f}")
        elif run:
            pts.append(run)
            run = []
    if run:
        pts.append(run)
    for run in pts:
        parts.append(f'<polyline points="{" ".join(run)}" fill="none" '
                     'stroke="#e6edf3" stroke-width="1.6"/>')
    # today marker
    g_last = np.nonzero(fin)[0]
    if len(g_last):
        gl = g_last[-1]
        cur = v[gl]
        col = pos_color if cur > 0 else neg_color
        lab = (pos_label if cur > 0 else neg_label)
        txt = f"{cur*100:+.2f}%" if pct else f"{cur:+.2f}"
        parts.append(f'<circle cx="{X(grid[gl]):.1f}" cy="{Y(cur):.1f}" r="5" '
                     f'fill="{col}"/>')
        parts.append(f'<text x="{x1}" y="13" text-anchor="end" class="now" '
                     f'fill="{col}">today {txt} — {lab}</text>')
    # scale labels
    parts.append(f'<text x="4" y="{Y(vmax)+10:.1f}" class="ax">'
                 f'{"+" if pct else ""}{vmax*100:.1f}%</text>')
    parts.append(f'<text x="4" y="{Y(-vmax):.1f}" class="ax">'
                 f'-{vmax*100:.1f}%</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def svg_btc(grid, bull, width=1120, height=56):
    x0, x1 = 50, width - 10
    t0, t1 = grid[0], grid[-1]
    def X(t): return x0 + (t - t0) / (t1 - t0) * (x1 - x0)
    parts = [f'<svg viewBox="0 0 {width} {height}" style="width:100%">']
    parts.append(f'<text x="{x0}" y="13" class="ttl">BTC trend (4h EMA20 vs '
                 'EMA50) — the live capit gate</text>')
    seg, cur = 0, bull[0]
    for g in range(1, len(grid) + 1):
        if g == len(grid) or bull[g] != cur:
            col = "#3fb950" if cur else "#f85149"
            parts.append(f'<rect x="{X(grid[seg]):.1f}" y="20" '
                         f'width="{X(grid[min(g, len(grid)-1)])-X(grid[seg]):.1f}"'
                         f' height="{height-26}" fill="{col}" opacity="0.5"/>')
            if g < len(grid):
                seg, cur = g, bull[g]
    state = "BULL" if bull[-1] else "BEAR"
    col = "#3fb950" if bull[-1] else "#f85149"
    parts.append(f'<text x="{x1}" y="13" text-anchor="end" class="now" '
                 f'fill="{col}">today: {state}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    tickers = load()
    t_end = max(d["t"][-1] for d in tickers.values())
    print(f"data through {pd.to_datetime(t_end, unit='ms')} UTC")
    pump = regime.pump_events_1h(tickers)
    dump = regime.dump_events_1h(tickers)
    print(f"pump events {len(pump[0]):,} | dump events {len(dump[0]):,}")
    g0 = int(pd.Timestamp("2023-03-01", tz="UTC").value // 10**6)
    grid = np.arange(g0, t_end + DAY, DAY)
    pd_s = regime.dial_series(pump, grid)
    dd_s = regime.dial_series(dump, grid)
    btc = tickers["BTC"]
    bull = regime.btc_trend_series(btc["t"], btc["c"], grid)

    cur_p = pd_s[np.isfinite(pd_s)][-1]
    cur_d = dd_s[np.isfinite(dd_s)][-1]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    short_season = "OPEN (pumps are dying)" if cur_p < 0 else \
        "CLOSED (pumps keep running)"
    long_season = "OPEN (dumps are bouncing)" if cur_d > 0 else \
        "CLOSED (dumps keep bleeding)"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Regime view</title><style>
body{{background:#0d1117;color:#e6edf3;font:14px/1.5 ui-monospace,Menlo,monospace;
max-width:1160px;margin:0 auto;padding:16px}}
h1{{font-size:18px;margin:0 0 4px}}
.sub{{color:#8b949e;font-size:12px;margin-bottom:14px}}
.cards{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;
padding:10px 16px;flex:1;min-width:240px}}
.card .v{{font-size:20px;font-weight:650}}
.card .l{{font-size:11px;color:#8b949e;text-transform:uppercase}}
.g{{color:#3fb950}}.r{{color:#f85149}}
.ttl{{fill:#8b949e;font-size:12px}}.ax{{fill:#555;font-size:10px}}
.now{{font-size:12px;font-weight:600}}
.box{{background:#161b22;border:1px solid #30363d;border-radius:8px;
padding:10px;margin-bottom:12px}}
.note{{color:#8b949e;font-size:12px;margin-top:10px}}
</style></head><body>
<h1>Regime view</h1>
<div class="sub">generated {stamp} · daily resolution · dials = trailing 30d
mean 24h-forward return of completed events (causal) · 1h-candle basis</div>
<div class="cards">
<div class="card"><div class="l">Short book season (pump dial)</div>
<div class="v {'r' if cur_p < 0 else 'g'}">{cur_p*100:+.2f}%</div>
<div>{short_season}</div></div>
<div class="card"><div class="l">Long book season (dump dial)</div>
<div class="v {'g' if cur_d > 0 else 'r'}">{cur_d*100:+.2f}%</div>
<div>{long_season}</div></div>
<div class="card"><div class="l">BTC trend gate</div>
<div class="v {'g' if bull[-1] else 'r'}">{'BULL' if bull[-1] else 'BEAR'}</div>
<div>capit gate {'CLOSED' if bull[-1] else 'OPEN'}</div></div>
</div>
<div class="box">{svg_strip(grid, pd_s,
    "PUMP dial — what happened to pumps, trailing 30d (below 0 = SHORT season)",
    "pumps run (short closed)", "pumps die (short open)",
    "#d29922", "#f85149")}</div>
<div class="box">{svg_strip(grid, dd_s,
    "DUMP dial — what happened to dumps, trailing 30d (above 0 = CAPIT-LONG season)",
    "dumps bounce (long open)", "dumps bleed (long closed)",
    "#3fb950", "#f85149")}</div>
<div class="box">{svg_btc(grid, bull)}</div>
<div class="note">Reading: the pump dial spent 2023-24 mostly positive
(continuation era — shorting pumps was fighting the tape) and flipped
negative through 2025-26 (exhaustion era — the current short book's
season). The dump dial is the long book's mirror: when it sits above zero,
capitulation longs get paid. Dials are event-outcome measurements, not
price shapes: each point answers "how did the last 30 days of
pumps/dumps actually resolve?"</div>
</body></html>"""
    os.makedirs("reports", exist_ok=True)
    out = "reports/regime_view.html"
    with open(out, "w") as f:
        f.write(html)
    print(f"pump dial today: {cur_p*100:+.2f}%  (short season "
          f"{'OPEN' if cur_p < 0 else 'closed'})")
    print(f"dump dial today: {cur_d*100:+.2f}%  (long season "
          f"{'OPEN' if cur_d > 0 else 'closed'})")
    print(f"BTC trend today: {'BULL' if bull[-1] else 'BEAR'}")
    print(f"[saved -> {out}]")


if __name__ == "__main__":
    main()
