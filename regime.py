#!/usr/bin/env python3
"""REGIME ENGINE — the one canonical home of the regime dials.

A dial is an event-outcome measurement, not a price shape: collect events
(pumps or dumps), measure each one's 24h-forward return, and read the
trailing 30d mean of COMPLETED outcomes. The reading decides which books
may trade.

SPEC (frozen — matches every backtest in reports/):
  pump event   : 4h runup >= +12% on an alive bar, 24h per-ticker cooldown
  dump event   : 24h return <= -10%, 24h per-ticker cooldown
  outcome      : close-to-close return over the next 24h
  dial reading : mean outcome of events completed inside the trailing 30d
                 window; needs >= 10 completed events, else no-read
  short book   : OPEN while pump dial m < 0       (exhaustion regime)
  momo long    : OPEN while pump dial m > +2%     (continuation regime)
  capit long   : OPEN while BTC 4h EMA20 <= EMA50 (bear trend)
  causality    : an event enters the dial only once its 24h outcome has
                 completed — every reading uses only the past, so the dial
                 is at least 24h stale by construction. Deliberate.

Two API layers, same spec:
  LIVE  (stdlib-only; dict candles + JSON event store):
        detect_pump_event, gate_state, ema_bull
  RESEARCH (numpy/pandas, imported lazily; cached candle arrays):
        alive, pump_events_15m, pump_events_1h, dump_events_1h,
        make_dial, dial_series, persistent_dial, btc_trend_series

Consumers: paper_fleet.py + hl_bot.py (live gate), research/
regime_switch_backtest.py (re-exports for the backtest scripts),
research/regime_view.py (dashboard), research/dial_persistence.py.
live/bot.py is deliberately NOT a consumer — it is the self-contained,
fingerprinted go-live package carrying byte-equivalent machinery.

Note: the 15m-candle dials (live gate, backtests) and the 1h-candle dials
(regime_view) are close cousins, not bit-identical — same spec, different
bar basis. Thresholds (0 short / +2% long) were tuned in-sample, not
pre-registered (reports/regime_policy_*.txt, twosided_system_*.txt).
"""
import time

M15 = 900_000
H1 = 3_600_000
DAY = 86_400_000

# ---- the frozen spec -------------------------------------------------------
PUMP_RUNUP = 0.12          # 4h runup defining a pump event
DUMP_DROP = -0.10          # 24h return defining a dump event
WINDOW_DAYS = 30           # trailing dial window
WINDOW_MS = WINDOW_DAYS * DAY
MIN_EV = 10                # completed events needed for a reading
FWD_MS = DAY               # outcome horizon
FWD_BARS_15M = 96          # same horizon in 15m bars
COOLDOWN_MS = DAY          # per-ticker event dedup
SHORT_THR = 0.0            # short book opens while m < -SHORT_THR
LONG_THR = 0.02            # momo long opens while m > LONG_THR (asymmetric)
EMA_FAST, EMA_SLOW = 20, 50   # BTC 4h trend gate


# ============================================================= LIVE LAYER
# stdlib-only: safe to import from the always-on fleet/bot processes.

def detect_pump_event(k, last_ev_t):
    """Pump event on the LAST CLOSED candle of dict-candle list k (15m).

    k: [{t,o,h,l,c,v}, ...]; last_ev_t: this ticker's previous event time
    (cooldown). Returns dict(t, px, runup) or None. Pure — the caller owns
    the store, the cooldown bookkeeping and the logging.
    """
    if not k or len(k) < 21:
        return None
    i = len(k) - 1
    if k[i]["t"] - last_ev_t < COOLDOWN_MS:
        return None
    if k[i]["t"] - k[i - 16]["t"] != 16 * M15:            # gapless 4h
        return None
    if any(x["v"] <= 0 for x in k[i - 8:i + 1]) or k[i]["h"] == k[i]["l"]:
        return None
    runup = k[i]["c"] / k[i - 16]["c"] - 1
    if runup < PUMP_RUNUP:
        return None
    return dict(t=k[i]["t"], px=k[i]["c"], runup=runup)


def gate_state(events, now=None):
    """Dial reading over a live event store -> dict(short, long, n, m).

    events: [{t, fwd, dead?, ...}, ...] — fwd is the 24h forward return,
    None until resolved. Only events that STARTED inside the trailing
    window AND whose outcome has completed (t + 24h <= now) count.
    short: m < 0 with >= MIN_EV events;  long: m > +2%.
    """
    if now is None:
        now = int(time.time() * 1000)
    done = [e["fwd"] for e in events
            if e["fwd"] is not None and not e.get("dead")
            and e["t"] >= now - WINDOW_MS
            and e["t"] + FWD_MS <= now]
    n = len(done)
    m = sum(done) / n if n else None
    return dict(short=(n >= MIN_EV and m < -SHORT_THR),
                long=(n >= MIN_EV and m > LONG_THR), n=n, m=m)


def ema_bull(closes, fast=EMA_FAST, slow=EMA_SLOW):
    """True when EMA(fast) > EMA(slow), both seeded at closes[0] — the
    adjust=False recursion every backtest and bot uses. BULL closes the
    capit gate; the short/long pump books don't look at this."""
    e_f = e_s = closes[0]
    for c in closes:
        e_f += (c - e_f) * 2 / (fast + 1)
        e_s += (c - e_s) * 2 / (slow + 1)
    return e_f > e_s


# ========================================================= RESEARCH LAYER
# numpy/pandas imported lazily so the live processes never pay for them.

def alive(d, i):
    """Bar i of ticker-dict d is tradeable: gapless 4h behind it, positive
    volume through the window, non-degenerate candle."""
    if i < 20:
        return False
    if d["t"][i] - d["t"][i - 16] != 16 * M15:
        return False
    vw = d["v"][i - 8:i + 1]
    return (vw > 0).all() and d["h"][i] != d["l"][i]


def pump_events_15m(tickers, fwd=FWD_BARS_15M, cooldown=FWD_BARS_15M):
    """Pump events on 15m candle arrays (the backtest/live-gate basis).
    -> (event_t, fwd24_ret, done_t) as sorted numpy arrays."""
    import numpy as np
    ev = []
    for tk, d in tickers.items():
        t, c = d["t"], d["c"]
        last = -10**18
        for i in range(20, len(t) - fwd):
            if t[i] - last < cooldown * M15:
                continue
            if not alive(d, i):
                continue
            if c[i] / c[i - 16] - 1 < PUMP_RUNUP:
                continue
            if t[i + fwd] - t[i] != fwd * M15:   # gap — no clean forward path
                continue
            ev.append((t[i], c[i + fwd] / c[i] - 1, t[i] + fwd * M15))
            last = t[i]
    ev.sort()
    return (np.array([e[0] for e in ev]),
            np.array([e[1] for e in ev]),
            np.array([e[2] for e in ev]))


def _events_1h(tickers, kind):
    """Pump/dump events on 1h close arrays (the regime_view basis).
    -> (event_t, fwd24_ret, done_t) as sorted numpy arrays."""
    import numpy as np
    ev = []
    for tk, d in tickers.items():
        t, c = d["t"], d["c"]
        n = len(t)
        last = -10**18
        for i in range(24, n - 24):
            if t[i] - last < DAY:
                continue
            if t[i] - t[i - 4] != 4 * H1 or t[i + 24] - t[i] != 24 * H1:
                continue
            if kind == "pump":
                if c[i] / c[i - 4] - 1 < PUMP_RUNUP:
                    continue
            else:
                if t[i] - t[i - 24] != 24 * H1:
                    continue
                if c[i] / c[i - 24] - 1 > DUMP_DROP:
                    continue
            ev.append((t[i], c[i + 24] / c[i] - 1, t[i] + DAY))
            last = t[i]
    ev.sort()
    return (np.array([e[0] for e in ev]), np.array([e[1] for e in ev]),
            np.array([e[2] for e in ev]))


def pump_events_1h(tickers):
    return _events_1h(tickers, "pump")


def dump_events_1h(tickers):
    return _events_1h(tickers, "dump")


def make_dial(ev_t, ev_r, ev_done, window_days=WINDOW_DAYS, thr=SHORT_THR,
              min_ev=MIN_EV):
    """-> dial(T) -> (state, n, m) with state in {-1 short, 0 flat, +1 long}.
    Causal: only events COMPLETED (done <= T) inside the trailing window."""
    from bisect import bisect_right
    import numpy as np
    order = np.argsort(ev_done)
    done_sorted, r_sorted, t_sorted = ev_done[order], ev_r[order], ev_t[order]

    def dial(T):
        hi = bisect_right(done_sorted, T)
        if hi == 0:
            return 0, 0, np.nan
        tmin = T - window_days * DAY
        mask = t_sorted[:hi] >= tmin
        n = int(mask.sum())
        if n < min_ev:
            return 0, n, np.nan
        m = float(r_sorted[:hi][mask].mean())
        if m < -thr:
            return -1, n, m
        if m > thr:
            return 1, n, m
        return 0, n, m
    return dial


def dial_series(ev, grid, window_ms=WINDOW_MS, min_ev=MIN_EV):
    """Dial mean sampled on a time grid (NaN where no reading) — the
    regime_view plotting series. ev = (event_t, fwd_ret, done_t)."""
    import numpy as np
    et, er, ed = ev
    order = np.argsort(ed)
    ed_s, er_s, et_s = ed[order], er[order], et[order]
    out = np.full(len(grid), np.nan)
    for g, T in enumerate(grid):
        hi = np.searchsorted(ed_s, T, "right")
        if hi == 0:
            continue
        mask = et_s[:hi] >= T - window_ms
        if mask.sum() < min_ev:
            continue
        out[g] = er_s[:hi][mask].mean()
    return out


def persistent_dial(dial, t0, t1, min_days):
    """Daily-sampled wrapper: reports -1 only once the dial has held -1 for
    min_days consecutive days (causal — uses only completed days). The
    flicker filter from the era20 finding: brief dial dips inside a buying
    regime let full-size shorts through; real short regimes hold for
    months (research/dial_persistence.py)."""
    import numpy as np
    days = np.arange(t0, t1 + DAY, DAY)
    state = np.array([dial(int(t))[0] for t in days])
    run = np.zeros(len(days), int)
    for i in range(len(days)):
        run[i] = (run[i - 1] + 1) if (state[i] == -1 and i > 0) \
            else (1 if state[i] == -1 else 0)

    def dial_p(T):
        s, n, m = dial(T)
        if s != -1:
            return s, n, m
        i = int(np.searchsorted(days, T, "right") - 1)
        if i < 0:
            return 0, n, m
        return (-1 if run[i] >= min_days else 0), n, m
    return dial_p


def btc_trend_series(t, c, grid):
    """BULL/BEAR (EMA20 vs EMA50 on 4h closes built from 1h data) sampled
    on a time grid -> bool array, True = BULL (capit gate closed)."""
    import numpy as np
    import pandas as pd
    s = pd.Series(c, index=t)
    b4 = s.groupby(lambda x: x - x % (4 * H1)).last()
    e_f = b4.ewm(span=EMA_FAST, adjust=False).mean()
    e_s = b4.ewm(span=EMA_SLOW, adjust=False).mean()
    t4 = b4.index.to_numpy() + 4 * H1          # signal known at candle CLOSE
    sig = (e_f > e_s).to_numpy()
    idx = np.searchsorted(t4, grid, "right") - 1
    return np.where(idx >= 0, sig[np.maximum(idx, 0)], True)
