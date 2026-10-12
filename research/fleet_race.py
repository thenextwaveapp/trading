#!/usr/bin/env python3
"""FLEET RACE — every fleet_config.json variant backtested on the Invo 60,
2025-26 main window, one table.

Engines mirror paper_fleet.py semantics: signal defs (signal/signal_momo/
signal_capit/run_churn/run_loser), check_exit replay (stop breach first,
trail ratchet, time exit), fleet account model ($10k, 0.75% risk / stop
distance, 20% notional cap, 6 concurrent (loser: slots = notional eq/slots,
same-ticker re-entry allowed), kill-switch 7d -5% -> 3d pause). superlarry
runs its own margin-floored engine (SL.run_book) — flagged in the table.

Usage: python3 research/fleet_race.py
Writes: reports/fleet_race_<stamp>.txt
"""
import json
from datetime import datetime, timezone

import numpy as np

from backtest import M15
from rules_backtest import load, alive, natr_at, TAKER, SLIP
from wf_engine import RISK, NOTIONAL_CAP, MAX_CONC, KILL_DD, KILL_LOOKBACK, \
    KILL_PAUSE
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
import super_larry as SL

COST = 2 * TAKER + SLIP
GATE_LONG_THR = 0.02

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


# ---------------------------------------------------------------- signals
def sig_pump_rows(tickers, cfg, dial):
    """Rule-P family + momo + two-sided. Row: (t_sig, tk, trade-dict)."""
    rows = []
    gate = cfg.get("gate") or cfg.get("twosided")
    veto = cfg.get("veto")
    for tk, d in tickers.items():
        t, o, h, l, c, v = (d[k] for k in "tohlcv")
        for i in range(20, len(t) - 1):
            if not alive(d, i):
                continue
            runup = c[i] / c[i - 16] - 1
            mu = v[i - 8:i].mean()
            t_sig = t[i] + M15
            # short book
            if (cfg.get("engine") != "momo" and runup >= cfg["runup"]
                    and c[i] < c[i - 1] and mu > 0 and v[i] / mu >= cfg["vol"]):
                ok = True
                if cfg.get("wick"):
                    O, Hh, Ll = o[i - 15], h[i - 15:i + 1].max(), l[i - 15:i + 1].min()
                    rng = Hh - Ll
                    ok = rng > 0 and (Hh - max(O, c[i])) / rng >= cfg["wick"]
                if ok and gate:
                    ok = dial(t_sig)[0] == -1
                if ok and veto:
                    s_, n_, m_ = dial(t_sig)
                    ok = not (m_ == m_ and m_ > veto)
                if ok:
                    mode, parm = cfg["stop"]
                    hh = h[i - 16:i + 1].max()
                    stop = hh * (1 + parm) if mode == "hh" else hh
                    na = natr_at(d, t_sig) if mode == "trail" else None
                    if mode != "trail" or na is not None:
                        rows.append((t_sig, tk, dict(
                            i=i, side=-1, entry=c[i], stop=stop,
                            hold=cfg["hold"],
                            trail_k=parm if mode == "trail" else None,
                            natr=na, sizing="risk")))
            # long book (momo engine or two-sided)
            if (cfg.get("engine") == "momo" or cfg.get("twosided")) \
                    and runup >= 0.12 and mu > 0 and v[i] / mu >= 2.5:
                O, Hh, Ll = o[i - 15], h[i - 15:i + 1].max(), l[i - 15:i + 1].min()
                rng = Hh - Ll
                if rng <= 0 or (Hh - max(O, c[i])) / rng > 0.15 \
                        or (c[i] - Ll) / rng < 0.80:
                    continue
                s_, n_, m_ = dial(t_sig)
                if not (m_ == m_ and m_ > GATE_LONG_THR):
                    continue
                stop = max(Ll, (O + c[i]) / 2) * 0.999
                rows.append((t_sig, tk, dict(
                    i=i, side=1, entry=c[i], stop=stop,
                    hold=48 if cfg.get("engine") == "momo" or cfg.get("twosided")
                    else cfg["hold"], trail_k=None, natr=None, sizing="risk")))
    rows.sort(key=lambda r: r[0])
    return rows


def sig_capit_rows(tickers, cfg, regime_at):
    rows = []
    only = set(cfg.get("only") or [])
    for tk, d in tickers.items():
        if only and tk not in only:
            continue
        t, h, l, c, v = (d[k] for k in "thlcv")
        r24 = d["drop96_v"]
        for i in range(97, len(t) - 1):
            if t[i] - t[i - 96] != 96 * M15:
                continue
            if (v[i - 8:i + 1] <= 0).any() or h[i] == l[i]:
                continue
            if not (r24[i] == r24[i] and r24[i] <= -cfg["depth"]):
                continue
            prev_ok = (t[i - 1] - t[i - 97] == 96 * M15
                       and r24[i - 1] == r24[i - 1]
                       and r24[i - 1] <= -cfg["depth"])
            if prev_ok:                                   # fresh crossing only
                continue
            t_sig = t[i] + M15
            if cfg.get("btc_bear") and regime_at(t_sig) is not False:
                continue
            na = natr_at(d, t_sig)
            sl_basis = max(2 * (na if na is not None else 0), 0.005)
            entry, j0 = c[i], i
            if cfg.get("limit"):                          # resting limit entry
                lim = c[i] * (1 - cfg["limit"])
                j0 = None
                for j in range(i + 1, min(i + 17, len(t))):
                    if l[j] <= lim:
                        entry, j0 = lim, j
                        break
                if j0 is None:
                    continue
            mode, parm = cfg["stop"]
            stop = entry * (1 - parm) if mode == "dstop" else None
            rows.append((t[j0] + M15, tk, dict(
                i=j0, side=1, entry=entry, stop=stop, hold=cfg["hold"],
                trail_k=None, natr=None, sizing="risk", sl_dist=sl_basis)))
    rows.sort(key=lambda r: r[0])
    return rows


def sig_hourly_rows(tickers, cfg):
    """churn / loser: every `every` bars pick the universe's biggest 1h
    move; churn fades it (stop at extreme), loser longs the dump."""
    cands = {}
    for tk, d in tickers.items():
        t, h, l, c, v = (d[k] for k in "thlcv")
        for i in range(5, len(t) - 1):
            if t[i] - t[i - 4] != 4 * M15:
                continue
            if (v[i - 4:i + 1] <= 0).any() or h[i] == l[i]:
                continue
            mv = c[i] / c[i - 4] - 1
            cands.setdefault(t[i], []).append((tk, mv, i))
    rows, last = [], -10**18
    churn = cfg.get("engine") == "churn"
    for ts in sorted(cands):
        t_sig = ts + M15
        if t_sig - last < cfg.get("every", 4) * M15:
            continue
        pool = cands[ts]
        tk, mv, i = (max(pool, key=lambda x: abs(x[1])) if churn
                     else min(pool, key=lambda x: x[1]))
        thr = cfg.get("min_move", 0.01 if churn else 0.02)
        if (abs(mv) if churn else -mv) < thr:
            continue
        d = tickers[tk]
        side = (-1 if mv > 0 else 1) if churn else 1
        stop = None
        if churn:
            stop = (d["h"][i - 4:i + 1].max() if side == -1
                    else d["l"][i - 4:i + 1].min())
        rows.append((t_sig, tk, dict(
            i=i, side=side, entry=d["c"][i], stop=stop, hold=cfg["hold"],
            trail_k=None, natr=None,
            sizing="slots" if not churn else "risk")))
        last = t_sig
    return rows


# ---------------------------------------------------------------- resolve
def resolve_trade(d, tr):
    """check_exit replay on arrays: breach first, trail ratchet, time exit."""
    i, side, entry = tr["i"], tr["side"], tr["entry"]
    level, low_min = tr["stop"], entry
    t, h, l, c = d["t"], d["h"], d["l"], d["c"]
    end = min(i + tr["hold"], len(t) - 1)
    for j in range(i + 1, end + 1):
        if level is not None and ((h[j] > level) if side < 0 else (l[j] < level)):
            return side * (level / entry - 1) - COST, t[j] + M15, "sl"
        if side < 0 and tr["trail_k"] and tr["natr"]:
            low_min = min(low_min, l[j])
            level = min(level, low_min * (1 + tr["trail_k"] * tr["natr"]))
    return side * (c[end] / entry - 1) - COST, t[end] + M15, "time"


def race(tickers, rows, cfg):
    """Fleet account model over chronologically ordered trade rows."""
    eq, peak, maxdd = START, START, 0.0
    eq_hist, pending, open_until = [], [], {}
    kill_until = 0
    slots = cfg.get("slots")
    nets, wins = [], 0
    for t_sig, tk, tr in rows:
        pending.sort()
        while pending and pending[0][0] <= t_sig:
            et, pnl = pending.pop(0)
            eq += pnl
            eq_hist.append((et, eq))
            peak = max(peak, eq)
            maxdd = min(maxdd, eq / peak - 1)
        if eq <= 0:
            break
        if t_sig < kill_until:
            continue
        hist = [e for e in eq_hist if e[0] >= t_sig - KILL_LOOKBACK]
        if hist and eq / max(e[1] for e in hist) - 1 < KILL_DD:
            kill_until = t_sig + KILL_PAUSE
            continue
        n_open = sum(1 for x in open_until.values() if x > t_sig)
        if slots:
            if n_open >= slots:
                continue
        else:
            if open_until.get(tk, 0) > t_sig or n_open >= MAX_CONC:
                continue
        d = tickers[tk]
        net, exit_t, kind = resolve_trade(d, tr)
        if tr["sizing"] == "slots":
            notional = eq / slots
        else:
            sl_dist = tr.get("sl_dist")
            if sl_dist is None:
                sl_dist = abs(tr["stop"] / tr["entry"] - 1) if tr["stop"] \
                    else 0.005
            notional = min(RISK * eq / max(abs(sl_dist), 0.005),
                           NOTIONAL_CAP * eq)
        pnl = notional * net
        pending.append((exit_t, pnl))
        if slots:
            open_until[f"{tk}@{t_sig}"] = exit_t     # re-entry allowed
        else:
            open_until[tk] = exit_t
        nets.append(net)
        wins += net > 0
    for et, pnl in sorted(pending):
        eq += pnl
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
    n = len(nets)
    return eq, maxdd, n, (np.mean(nets) if n else float("nan")), \
        (wins / n if n else float("nan"))


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"FLEET RACE — {stamp} | Invo 60, 2025-26 main window "
      "(2024-12-15 .. 2026-10-03)")
    p("fleet account model: $10k, 0.75% risk/stop-dist, 20% cap, conc 6, "
      "kill 7d-5%; loser eq/slots; superlarry own margin engine")
    p("")

    tickers, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    for d in tickers.values():
        precompute(d)
    ev = pump_events(tickers)
    dial = make_dial(*ev, 30, 0.0)
    p(f"loaded {len(tickers)} tickers | pump events {len(ev[0]):,}")
    p("")
    p(f"{'variant':12s} {'$10k ->':>11s} {'ret%':>8s} {'maxdd':>7s} "
      f"{'trades':>6s} {'win%':>5s} {'avg net':>8s}")

    cfgs = json.load(open("fleet_config.json"))["strategies"]
    results = []
    for sk, s in cfgs.items():
        for vn, v in s["variants"].items():
            cfg = {k: x for k, x in v.items() if k not in ("bt", "note")}
            cfg["stop"] = tuple(cfg["stop"]) if "stop" in cfg else ("none", 0)
            if cfg.get("engine") == "super":
                eq, maxdd, n_s, n_c, sk_, lq = SL.run_book(
                    tickers, dial, regime_at,
                    {k: tuple(x) for k, x in cfg["sizing"].items()})
                results.append((vn, eq, maxdd, n_s + n_c, float("nan"),
                                float("nan")))
                p(f"{vn:12s} ${eq:>10,.0f} {(eq/START-1)*100:+7.1f}% "
                  f"{maxdd*100:6.1f}% {n_s + n_c:6d} {'':>5s} {'':>8s}  *margin engine")
                continue
            if cfg.get("engine") in ("churn", "loser"):
                rows = sig_hourly_rows(tickers, cfg)
            elif cfg.get("engine") == "capit":
                rows = sig_capit_rows(tickers, cfg, regime_at)
            else:
                rows = sig_pump_rows(tickers, cfg, dial)
            eq, maxdd, n, avg, win = race(tickers, rows, cfg)
            results.append((vn, eq, maxdd, n, avg, win))
            p(f"{vn:12s} ${eq:>10,.0f} {(eq/START-1)*100:+7.1f}% "
              f"{maxdd*100:6.1f}% {n:6d} {win*100:4.0f}% {avg*100:+7.2f}%")

    p("")
    p("podium (by final equity):")
    for vn, eq, maxdd, *_ in sorted(results, key=lambda r: -r[1])[:5]:
        p(f"  {vn:12s} ${eq:,.0f}  (dd {maxdd*100:.1f}%)")

    fname = ("reports/fleet_race_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
