#!/usr/bin/env python3
"""Does picking the biggest hourly loser add anything over being long at
the same moments?

At every base-rule entry timestamp (thr 2%, hold 24h, time exit), also
"buy" two stand-ins with identical hold and costs: BTC, and the alive coin
whose 1h return is the median that hour. Report per BTC-r24 bucket: the
loser pick, the stand-ins, and the spread (pick minus median coin) — the
selection rule's own contribution with the market's move subtracted.
"""
import sys
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(1, os.path.join(_here, "_archive"))
from regime_switch_backtest import load_full                    # noqa: E402
from hourly_explore import precompute, build_panel              # noqa: E402
from loser_variants_backtest import path_exit, OUT, p           # noqa: E402

E0 = {"kind": "time"}
HOLD = 96


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tickers = load_full()
    for d in tickers.values():
        precompute(d)
    grid, tks, panel = build_panel(tickers)
    p(f"LOSER PICK vs SAME-TIMESTAMP STAND-INS — {stamp}")
    p("entry: biggest 1h loser <= -2% | stand-ins at same hour: BTC, median-r1 coin")
    p("all legs: buy close, time exit 24h, cost 0.14%\n")

    r1m = np.where(panel["alive"], panel["r1"], np.nan)
    btc = tickers["BTC"]
    bidx = {int(t): i for i, t in enumerate(btc["t"])}

    rows = []
    open_until = {}
    for r in range(len(grid)):
        row = r1m[r]
        if np.all(np.isnan(row)):
            continue
        T = int(grid[r])
        j = int(np.nanargmin(row))
        if np.isnan(row[j]) or row[j] > -0.02:
            continue
        tk = tks[j]
        d = tickers[tk]
        res = path_exit(d, panel["idx"][r, j], HOLD, E0)
        if res is None:
            continue
        open_until[tk] = T + HOLD * 900_000
        # stand-in 1: BTC at the same hour
        bi = bidx.get(T)
        btc_net = None
        btc_r24 = None
        if bi is not None:
            b = path_exit(btc, bi, HOLD, E0)
            btc_net = b[0] if b else None
            btc_r24 = btc["r24_v"][bi]
        # stand-in 2: the median-r1 alive coin that hour
        alive = np.where(~np.isnan(row))[0]
        med_net = None
        if len(alive):
            mj = alive[np.argsort(row[alive])[len(alive) // 2]]
            m = path_exit(tickers[tks[mj]], panel["idx"][r, mj], HOLD, E0)
            med_net = m[0] if m else None
        rows.append(dict(t=T, net=res[0], btc=btc_net, med=med_net,
                         btc24=btc_r24))

    g = pd.DataFrame(rows)
    g["year"] = pd.to_datetime(g["t"], unit="ms").dt.year
    p(f"trades: {len(g):,}\n")

    edges = [-1, -0.05, -0.02, 0, 0.02, 10]
    labels = ["<= -5%", "-5..-2%", "-2..0%", "0..+2%", "> +2%"]
    g["b"] = pd.cut(g["btc24"], edges, labels=labels)

    p(f"{'btc24 bucket':14s} {'n':>6s} {'loser pick':>11s} {'BTC':>8s} "
      f"{'median coin':>12s} {'pick - median':>14s}")
    for lab in ["ALL"] + labels:
        s = g if lab == "ALL" else g[g["b"] == lab]
        s = s.dropna(subset=["med", "btc"])
        if not len(s):
            continue
        sp = (s["net"] - s["med"])
        p(f"{lab:14s} {len(s):6,} {s['net'].mean()*100:+10.3f}% "
          f"{s['btc'].mean()*100:+7.3f}% {s['med'].mean()*100:+11.3f}% "
          f"{sp.mean()*100:+13.3f}%")
    p("")
    p("spread (pick - median coin) by year:")
    for y in sorted(g["year"].unique()):
        s = g[g["year"] == y].dropna(subset=["med"])
        sp = s["net"] - s["med"]
        p(f"  {y}  n {len(s):6,}  spread {sp.mean()*100:+.3f}%  "
          f"(pick {s['net'].mean()*100:+.3f}% / median {s['med'].mean()*100:+.3f}%)")

    out = os.path.join(os.path.dirname(_here), "reports",
                       f"loser_control_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt")
    open(out, "w").write("\n".join(OUT) + "\n")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
