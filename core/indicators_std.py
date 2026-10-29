"""Standard indicators in pure Python — dependency-free, registered in core.

These are the commonly-used TA-Lib indicators the Builder/parser advertise
(RSI, EMA, SMA, ATR, MACD, Bollinger, …), reimplemented with no C dependency so
the engine resolves them on EVERY host — the training worker, the live fleet,
and the lab — not only where the TA-Lib C library happens to be installed. They
register BEFORE core/talib_wrap, so these ids win and are identical everywhere;
TA-Lib (when present) only fills the long tail it uniquely provides.

Each implementation is validated to match TA-Lib within a tight tolerance
(tests/selftest_indicators_std.py), including first-valid-bar alignment, so the
switch is value-for-value transparent.

Convention (shared with core/indicators.py): fn(candles, **params) ->
list[float|None] aligned to candles; None during warmup. Param names mirror the
spec/TA-Lib (`timeperiod`, `fastperiod`, …).
"""
from .indicators import Indicator, REGISTRY, register


# --------------------------------------------------------------------------- #
# series helpers (operate on plain float lists)
# --------------------------------------------------------------------------- #
def _closes(candles):
    return [x["c"] for x in candles]


def _sma_series(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _ema_series(vals, n):
    """TA-Lib EMA: seed = SMA of first n values at index n-1, then recurse."""
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    seed = sum(vals[:n]) / n
    out[n - 1] = seed
    k = 2.0 / (n + 1)
    prev = seed
    for i in range(n, len(vals)):
        prev = vals[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _true_range(candles):
    tr = [None] * len(candles)
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i - 1]["c"]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
    return tr


# --------------------------------------------------------------------------- #
# indicators
# --------------------------------------------------------------------------- #
def _sma(candles, timeperiod=30):
    return _sma_series(_closes(candles), int(timeperiod))


def _ema(candles, timeperiod=30):
    return _ema_series(_closes(candles), int(timeperiod))


def _wma(candles, timeperiod=30):
    c = _closes(candles)
    n = int(timeperiod)
    out = [None] * len(c)
    denom = n * (n + 1) / 2
    for i in range(n - 1, len(c)):
        acc = 0.0
        for j in range(n):
            acc += c[i - n + 1 + j] * (j + 1)
        out[i] = acc / denom
    return out


def _dema(candles, timeperiod=30):
    n = int(timeperiod)
    e = _ema_series(_closes(candles), n)
    ee = _ema_series([x for x in e if x is not None], n)
    out = [None] * len(candles)
    off = n - 1  # where e starts
    for i in range(len(candles)):
        k = i - off
        if 0 <= k < len(ee) and ee[k] is not None and e[i] is not None:
            out[i] = 2 * e[i] - ee[k]
    return out


def _tema(candles, timeperiod=30):
    n = int(timeperiod)
    c = _closes(candles)
    e = _ema_series(c, n)
    e_vals = [x for x in e if x is not None]
    ee = _ema_series(e_vals, n)
    ee_vals = [x for x in ee if x is not None]
    eee = _ema_series(ee_vals, n)
    out = [None] * len(candles)
    off = n - 1
    for i in range(len(candles)):
        k1 = i - off           # index into ee
        k2 = i - 2 * off       # index into eee
        if k2 >= 0 and k2 < len(eee) and eee[k2] is not None and 0 <= k1 < len(ee) and ee[k1] is not None and e[i] is not None:
            out[i] = 3 * e[i] - 3 * ee[k1] + eee[k2]
    return out


def _rsi(candles, timeperiod=14):
    c = _closes(candles)
    n = int(timeperiod)
    out = [None] * len(c)
    if len(c) <= n:
        return out
    gain = loss = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        gain += d if d > 0 else 0.0
        loss += -d if d < 0 else 0.0
    gain /= n
    loss /= n
    out[n] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        gain = (gain * (n - 1) + (d if d > 0 else 0.0)) / n
        loss = (loss * (n - 1) + (-d if d < 0 else 0.0)) / n
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def _cmo(candles, timeperiod=14):
    c = _closes(candles)
    n = int(timeperiod)
    out = [None] * len(c)
    if len(c) <= n:
        return out
    su = sd = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        su += d if d > 0 else 0.0
        sd += -d if d < 0 else 0.0
    su /= n
    sd /= n
    out[n] = 0.0 if (su + sd) == 0 else 100 * (su - sd) / (su + sd)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        su = (su * (n - 1) + (d if d > 0 else 0.0)) / n
        sd = (sd * (n - 1) + (-d if d < 0 else 0.0)) / n
        out[i] = 0.0 if (su + sd) == 0 else 100 * (su - sd) / (su + sd)
    return out


def _mom(candles, timeperiod=10):
    c = _closes(candles)
    n = int(timeperiod)
    out = [None] * len(c)
    for i in range(n, len(c)):
        out[i] = c[i] - c[i - n]
    return out


def _atr(candles, timeperiod=14):
    n = int(timeperiod)
    tr = _true_range(candles)
    out = [None] * len(candles)
    if len(candles) <= n:
        return out
    prev = sum(tr[1:n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(candles)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def _natr(candles, timeperiod=14):
    atr = _atr(candles, timeperiod)
    out = [None] * len(candles)
    for i, a in enumerate(atr):
        c = candles[i]["c"]
        if a is not None and c:
            out[i] = 100 * a / c
    return out


def _willr(candles, timeperiod=14):
    n = int(timeperiod)
    out = [None] * len(candles)
    for i in range(n - 1, len(candles)):
        seg = candles[i - n + 1:i + 1]
        hh = max(x["h"] for x in seg)
        ll = min(x["l"] for x in seg)
        rng = hh - ll
        out[i] = 0.0 if rng == 0 else -100.0 * (hh - candles[i]["c"]) / rng
    return out


def _cci(candles, timeperiod=14):
    n = int(timeperiod)
    tp = [(x["h"] + x["l"] + x["c"]) / 3 for x in candles]
    out = [None] * len(candles)
    for i in range(n - 1, len(candles)):
        seg = tp[i - n + 1:i + 1]
        ma = sum(seg) / n
        md = sum(abs(x - ma) for x in seg) / n
        out[i] = 0.0 if md == 0 else (tp[i] - ma) / (0.015 * md)
    return out


def _mfi(candles, timeperiod=14):
    n = int(timeperiod)
    tp = [(x["h"] + x["l"] + x["c"]) / 3 for x in candles]
    rmf = [tp[i] * candles[i]["v"] for i in range(len(candles))]
    pos = [0.0] * len(candles)
    neg = [0.0] * len(candles)
    for i in range(1, len(candles)):
        if tp[i] > tp[i - 1]:
            pos[i] = rmf[i]
        elif tp[i] < tp[i - 1]:
            neg[i] = rmf[i]
    out = [None] * len(candles)
    for i in range(n, len(candles)):
        p = sum(pos[i - n + 1:i + 1])
        ng = sum(neg[i - n + 1:i + 1])
        out[i] = 100.0 if ng == 0 else 100 - 100 / (1 + p / ng)
    return out


def _obv(candles):
    out = [None] * len(candles)
    if not candles:
        return out
    obv = candles[0]["v"]
    out[0] = obv
    for i in range(1, len(candles)):
        if candles[i]["c"] > candles[i - 1]["c"]:
            obv += candles[i]["v"]
        elif candles[i]["c"] < candles[i - 1]["c"]:
            obv -= candles[i]["v"]
        out[i] = obv
    return out


def _macd_parts(candles, fastperiod=12, slowperiod=26, signalperiod=9):
    c = _closes(candles)
    fast, slow, sig = int(fastperiod), int(slowperiod), int(signalperiod)
    ef = _ema_series(c, fast)
    es = _ema_series(c, slow)
    macd = [None] * len(c)
    for i in range(len(c)):
        if ef[i] is not None and es[i] is not None:
            macd[i] = ef[i] - es[i]
    start = slow - 1  # first index macd is defined
    macd_defined = macd[start:]
    sig_sub = _ema_series(macd_defined, sig)
    signal = [None] * len(c)
    for k, v in enumerate(sig_sub):
        if v is not None:
            signal[start + k] = v
    hist = [None] * len(c)
    for i in range(len(c)):
        if macd[i] is not None and signal[i] is not None:
            hist[i] = macd[i] - signal[i]
    return macd, signal, hist


def _macd_out(idx):
    def fn(candles, fastperiod=12, slowperiod=26, signalperiod=9):
        return _macd_parts(candles, fastperiod, slowperiod, signalperiod)[idx]
    return fn


def _bbands_parts(candles, timeperiod=5, nbdevup=2.0, nbdevdn=2.0):
    c = _closes(candles)
    n = int(timeperiod)
    mid = _sma_series(c, n)
    up = [None] * len(c)
    lo = [None] * len(c)
    for i in range(n - 1, len(c)):
        m = mid[i]
        seg = c[i - n + 1:i + 1]
        var = sum((x - m) ** 2 for x in seg) / n   # population stdev (TA-Lib)
        sd = var ** 0.5
        up[i] = m + nbdevup * sd
        lo[i] = m - nbdevdn * sd
    return up, mid, lo


def _bb_out(idx):
    def fn(candles, timeperiod=5, nbdevup=2.0, nbdevdn=2.0):
        return _bbands_parts(candles, timeperiod, nbdevup, nbdevdn)[idx]
    return fn


def _adx(candles, timeperiod=14):
    n = int(timeperiod)
    length = len(candles)
    out = [None] * length
    if length < 2 * n:
        return out
    pdm = [0.0] * length
    mdm = [0.0] * length
    tr = [0.0] * length
    for i in range(1, length):
        up = candles[i]["h"] - candles[i - 1]["h"]
        dn = candles[i - 1]["l"] - candles[i]["l"]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        h, l, pc = candles[i]["h"], candles[i]["l"], candles[i - 1]["c"]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
    sTR = sum(tr[1:n + 1])
    sP = sum(pdm[1:n + 1])
    sM = sum(mdm[1:n + 1])

    def _dx(sP, sM, sTR):
        pDI = 100 * sP / sTR if sTR else 0.0
        mDI = 100 * sM / sTR if sTR else 0.0
        s = pDI + mDI
        return 0.0 if s == 0 else 100 * abs(pDI - mDI) / s

    dx = [None] * length
    dx[n] = _dx(sP, sM, sTR)
    for i in range(n + 1, length):
        sTR = sTR - sTR / n + tr[i]
        sP = sP - sP / n + pdm[i]
        sM = sM - sM / n + mdm[i]
        dx[i] = _dx(sP, sM, sTR)
    first = sum(dx[n:2 * n]) / n
    out[2 * n - 1] = first
    prev = first
    for i in range(2 * n, length):
        prev = (prev * (n - 1) + dx[i]) / n
        out[i] = prev
    return out


# --------------------------------------------------------------------------- #
# registration (only ids not already present; native ROC/VOL_RATIO/… keep theirs)
# --------------------------------------------------------------------------- #
_PERIOD = lambda d: (("timeperiod", int, d, 1, 1000),)
_C = ("close",)
_HLC = ("high", "low", "close")

_STD = [
    ("SMA", _sma, lambda p: int(p.get("timeperiod", 30)) - 1, "Simple Moving Average", "overlap", _C, _PERIOD(30)),
    ("EMA", _ema, lambda p: int(p.get("timeperiod", 30)) - 1, "Exponential Moving Average", "overlap", _C, _PERIOD(30)),
    ("WMA", _wma, lambda p: int(p.get("timeperiod", 30)) - 1, "Weighted Moving Average", "overlap", _C, _PERIOD(30)),
    ("DEMA", _dema, lambda p: 2 * (int(p.get("timeperiod", 30)) - 1), "Double EMA", "overlap", _C, _PERIOD(30)),
    ("TEMA", _tema, lambda p: 3 * (int(p.get("timeperiod", 30)) - 1), "Triple EMA", "overlap", _C, _PERIOD(30)),
    ("RSI", _rsi, lambda p: int(p.get("timeperiod", 14)), "Relative Strength Index", "momentum", _C, _PERIOD(14)),
    ("CMO", _cmo, lambda p: int(p.get("timeperiod", 14)), "Chande Momentum Oscillator", "momentum", _C, _PERIOD(14)),
    ("MOM", _mom, lambda p: int(p.get("timeperiod", 10)), "Momentum", "momentum", _C, _PERIOD(10)),
    ("ATR", _atr, lambda p: int(p.get("timeperiod", 14)), "Average True Range", "volatility", _HLC, _PERIOD(14)),
    ("NATR", _natr, lambda p: int(p.get("timeperiod", 14)), "Normalized ATR", "volatility", _HLC, _PERIOD(14)),
    ("WILLR", _willr, lambda p: int(p.get("timeperiod", 14)) - 1, "Williams %R", "momentum", _HLC, _PERIOD(14)),
    ("CCI", _cci, lambda p: int(p.get("timeperiod", 14)) - 1, "Commodity Channel Index", "momentum", _HLC, _PERIOD(14)),
    ("MFI", _mfi, lambda p: int(p.get("timeperiod", 14)), "Money Flow Index", "momentum", ("high", "low", "close", "volume"), _PERIOD(14)),
    ("ADX", _adx, lambda p: 2 * int(p.get("timeperiod", 14)) - 1, "Average Directional Index", "momentum", _HLC, _PERIOD(14)),
    ("OBV", _obv, lambda p: 0, "On Balance Volume", "volume", ("close", "volume"), ()),
    ("MACD_macd", _macd_out(0), lambda p: int(p.get("slowperiod", 26)) - 1, "MACD", "momentum", _C,
     (("fastperiod", int, 12, 1, 1000), ("slowperiod", int, 26, 1, 1000), ("signalperiod", int, 9, 1, 1000))),
    ("MACD_macdsignal", _macd_out(1), lambda p: int(p.get("slowperiod", 26)) + int(p.get("signalperiod", 9)) - 2, "MACD Signal", "momentum", _C,
     (("fastperiod", int, 12, 1, 1000), ("slowperiod", int, 26, 1, 1000), ("signalperiod", int, 9, 1, 1000))),
    ("MACD_macdhist", _macd_out(2), lambda p: int(p.get("slowperiod", 26)) + int(p.get("signalperiod", 9)) - 2, "MACD Histogram", "momentum", _C,
     (("fastperiod", int, 12, 1, 1000), ("slowperiod", int, 26, 1, 1000), ("signalperiod", int, 9, 1, 1000))),
    ("BBANDS_upperband", _bb_out(0), lambda p: int(p.get("timeperiod", 5)) - 1, "Bollinger Upper", "volatility", _C,
     (("timeperiod", int, 5, 1, 1000), ("nbdevup", float, 2.0, 0, 100), ("nbdevdn", float, 2.0, 0, 100))),
    ("BBANDS_middleband", _bb_out(1), lambda p: int(p.get("timeperiod", 5)) - 1, "Bollinger Middle", "volatility", _C,
     (("timeperiod", int, 5, 1, 1000), ("nbdevup", float, 2.0, 0, 100), ("nbdevdn", float, 2.0, 0, 100))),
    ("BBANDS_lowerband", _bb_out(2), lambda p: int(p.get("timeperiod", 5)) - 1, "Bollinger Lower", "volatility", _C,
     (("timeperiod", int, 5, 1, 1000), ("nbdevup", float, 2.0, 0, 100), ("nbdevdn", float, 2.0, 0, 100))),
]


def load():
    for ind_id, fn, lb, label, cat, inputs, params in _STD:
        if ind_id in REGISTRY:
            continue
        register(Indicator(id=ind_id, fn=fn, lookback=lb, label=label, category=cat, inputs=inputs, params=params))


load()
