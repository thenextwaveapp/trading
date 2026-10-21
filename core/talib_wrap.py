"""Register the full TA-Lib indicator set behind core's indicator interface.

On import this iterates every TA-Lib function and registers it into the
shared REGISTRY — canonical reference implementations, auto-discovered from
TA-Lib's own abstract-API metadata (params, defaults, outputs, lookback), so
the whole standard library comes in with one adapter instead of 150 hand
wrappers.

Rules of the wrap:
  - Only indicator groups are included; the Math Operators / Math Transform
    utility groups (ADD, SUB, SIN, LN, …) are skipped — they are not
    indicators.
  - A function is skipped if it needs an input outside OHLCV (e.g. MAVP's
    `periods` array) — it can't be driven from candles alone.
  - Multi-output functions (MACD, BBANDS, STOCH, …) register one indicator
    per output, id = NAME_<output> (e.g. MACD_macd, MACD_macdsignal).
  - An id already in the REGISTRY is left untouched (our fraction-form ROC
    and the custom VOL_RATIO / WICK_FRAC win over any TA-Lib namesake).

If TA-Lib is not installed, this module registers nothing and sets
TALIB_AVAILABLE = False, so `core` still imports (with just the custom
indicators). TA-Lib is a product dependency; install it on any box that runs
backtests.
"""
from .indicators import REGISTRY, Indicator, register

OHLCV = {"open", "high", "low", "close", "volume"}
SKIP_GROUPS = {"Math Operators", "Math Transform"}

TALIB_AVAILABLE = False
REGISTERED = []
SKIPPED = []


def _columns(input_names):
    cols = []
    for v in input_names.values():
        cols.extend(v if isinstance(v, list) else [v])
    return cols


def _make_fn(name, out_idx, multi):
    def fn(candles, _name=name, _idx=out_idx, _multi=multi, **params):
        import numpy as np
        from talib import abstract
        inp = {
            "open": np.array([x["o"] for x in candles], dtype=float),
            "high": np.array([x["h"] for x in candles], dtype=float),
            "low": np.array([x["l"] for x in candles], dtype=float),
            "close": np.array([x["c"] for x in candles], dtype=float),
            "volume": np.array([x["v"] for x in candles], dtype=float),
        }
        res = abstract.Function(_name)(inp, **params)
        arr = res[_idx] if _multi else res
        return [None if x != x else float(x) for x in arr]   # NaN -> None
    return fn


def _make_lookback(name):
    def lookback(params, _name=name):
        from talib import abstract
        f = abstract.Function(_name)
        if params:
            f.set_parameters(**{k: v for k, v in params.items()
                                if k in f.parameters})
        return f.lookback
    return lookback


def load():
    global TALIB_AVAILABLE
    try:
        import talib
        from talib import abstract
    except Exception:
        return
    TALIB_AVAILABLE = True

    for name in talib.get_functions():
        f = abstract.Function(name)
        info = f.info
        group = info["group"]
        if group in SKIP_GROUPS:
            SKIPPED.append((name, "utility group"))
            continue
        if any(c not in OHLCV for c in _columns(info["input_names"])):
            SKIPPED.append((name, "non-OHLCV input"))
            continue

        params = tuple((pn, type(pd), pd, None, None)
                       for pn, pd in f.parameters.items())
        inputs = tuple(_columns(info["input_names"]))
        outputs = info["output_names"]
        multi = len(outputs) > 1
        lb = _make_lookback(name)

        for idx, out in enumerate(outputs):
            ind_id = f"{name}_{out}" if multi else name
            if ind_id in REGISTRY:
                SKIPPED.append((ind_id, "id already registered"))
                continue
            register(Indicator(
                id=ind_id,
                fn=_make_fn(name, idx, multi),
                lookback=lb,
                label=info.get("display_name", name),
                category=group,
                inputs=inputs,
                params=params,
            ))
            REGISTERED.append(ind_id)


load()
