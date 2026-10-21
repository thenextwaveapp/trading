"""The weld — convert legacy fleet_config / pf_bots.params into the canonical
core strategy spec.

Existing bots store strategy as (family_slug + params jsonb), e.g.
    pump_short  {"runup": 0.12, "vol": 2.0, "hold": 16, "stop": ["hh", 0.0]}
    capit_long  {"depth": 0.2, "hold": 96, "stop": ["none", 0.0], "btc_bear": true}

This module turns those into the composable spec the engine runs (indicators →
conditions). That makes one source of truth: build in Studio, store the spec,
run it live, let others copy it — all the same object.

Coverage: pump_short, two_sided (short book), capit_long, momo_long map
cleanly. The regime/book engines (super, portfolio, churn, hourly_loser) carry
engine-specific logic not yet expressible as pure indicator conditions — they
return a spec marked {"partial": true} with whatever maps, so nothing breaks.
"""


def _stop(stop):
    """Legacy [mode, param] -> exit.stop dict. hh carries the 4h window."""
    mode, param = (stop + [0.0])[:2] if isinstance(stop, list) else ("none", 0.0)
    if mode == "hh":
        return {"mode": "hh", "window": 16, "param": param}
    if mode in ("dstop", "trail"):
        return {"mode": mode, "param": param}
    return {"mode": mode, "param": 0.0}


def _filters(p):
    f = []
    if p.get("btc_bear"):
        f.append({"kind": "btc_bear"})
    if p.get("veto") is not None:
        f.append({"kind": "regime_veto", "threshold": p["veto"]})
    if p.get("only"):
        f.append({"kind": "universe", "only": p["only"]})
    return f


def _pump_entry(p):
    children = [
        {"left": {"ind": "ROC", "params": {"period": 16}}, "op": "ge",
         "right": p.get("runup", 0.12)},
        {"left": {"ind": "close"}, "op": "lt",
         "right": {"ind": "close", "offset": -1}},
        {"left": {"ind": "VOL_RATIO", "params": {"period": 8}}, "op": "ge",
         "right": p.get("vol", 2.0)},
    ]
    if p.get("wick") is not None:
        children.append({"left": {"ind": "WICK_FRAC", "params": {"period": 16}},
                         "op": "ge", "right": p["wick"]})
    return {"logic": "AND", "children": children}


def variant_to_spec(family, params, name="", market="crypto_perp",
                    universe="invo60"):
    """Map (family_slug, params) -> canonical strategy spec dict."""
    p = dict(params or {})
    base = {"name": name, "market": market, "universe": universe,
            "sizing": {"risk": 0.0075, "notional_cap": 0.20, "weight": 1.0},
            "filters": _filters(p)}

    if family in ("pump_short", "two_sided"):
        return {**base, "side": "short", "fresh": False,
                "entry": _pump_entry(p),
                "exit": {"time_bars": p.get("hold", 16),
                         "stop": _stop(p.get("stop", ["hh", 0.0]))},
                "partial": family == "two_sided"}  # long book not mapped

    if family == "capit_long":
        exit_ = {"time_bars": p.get("hold", 96),
                 "stop": _stop(p.get("stop", ["none", 0.0]))}
        if p.get("limit") is not None:
            exit_["limit"] = p["limit"]
        return {**base, "side": "long", "fresh": True,
                "entry": {"logic": "AND", "children": [
                    {"left": {"ind": "ROC", "params": {"period": 96}},
                     "op": "le", "right": -p.get("depth", 0.2)}]},
                "exit": exit_}

    if family == "momo_long":
        # clean high-volume breakout that closes strong; stop from the signal
        # window (max(window low, midpoint) - 0.1%). Fully expressible now.
        return {**base, "side": "long", "fresh": False,
                "entry": {"logic": "AND", "children": [
                    {"left": {"ind": "ROC", "params": {"period": 16}},
                     "op": "ge", "right": 0.12},
                    {"left": {"ind": "VOL_RATIO", "params": {"period": 8}},
                     "op": "ge", "right": 2.5},
                    {"left": {"ind": "WICK_FRAC", "params": {"period": 16}},
                     "op": "le", "right": 0.15},
                    {"left": {"ind": "CLOSE_POS", "params": {"period": 16}},
                     "op": "ge", "right": 0.80}]},
                "exit": {"time_bars": p.get("hold", 48),
                         "stop": {"mode": "sig", "window": 16, "param": 0.001}}}

    # super / portfolio / churn / hourly_loser — engine-specific, not yet
    # expressible as pure indicator conditions
    return {**base, "side": "both", "fresh": False,
            "entry": {"logic": "AND", "children": []},
            "exit": {"time_bars": p.get("hold", 96),
                     "stop": _stop(p.get("stop", ["none", 0.0]))},
            "partial": True, "engine": family}
