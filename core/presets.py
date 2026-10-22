"""Seed presets — the founder's frozen rules expressed as compositions.

These are the proof the composable model captures the hand-coded engines:
RULE_P is paper_fleet.signal() base, RULE_P_WICK adds the wick filter, and
CAPIT is signal_capit(). In the product these become entries in the preset
gallery; nothing about them is special — each is just a Strategy.
"""

# pump-short base (Rule P, frozen) — paper_fleet.signal() with base cfg
RULE_P = {
    "name": "pump-short base",
    "side": "short",
    "market": "crypto_perp",
    "universe": "fleet-60",
    "entry": {"logic": "AND", "children": [
        {"left": {"ind": "ROC", "params": {"period": 16}}, "op": "ge",
         "right": 0.12},
        {"left": {"ind": "close"}, "op": "lt",
         "right": {"ind": "close", "offset": -1}},
        {"left": {"ind": "VOL_RATIO", "params": {"period": 8}}, "op": "ge",
         "right": 2.0},
    ]},
    "exit": {"time_bars": 16, "stop": {"mode": "hh", "param": 0.0}},
    "sizing": {"risk": 0.0075, "notional_cap": 0.20, "weight": 1.0},
}

# pump-short + upper-wick >= 30% (the wick30 variant)
RULE_P_WICK = {
    "name": "pump-short wick30",
    "side": "short",
    "market": "crypto_perp",
    "universe": "fleet-60",
    "entry": {"logic": "AND", "children": [
        {"left": {"ind": "ROC", "params": {"period": 16}}, "op": "ge",
         "right": 0.12},
        {"left": {"ind": "close"}, "op": "lt",
         "right": {"ind": "close", "offset": -1}},
        {"left": {"ind": "VOL_RATIO", "params": {"period": 8}}, "op": "ge",
         "right": 2.0},
        {"left": {"ind": "WICK_FRAC", "params": {"period": 16}}, "op": "ge",
         "right": 0.3},
    ]},
    "exit": {"time_bars": 16, "stop": {"mode": "hh", "param": 0.0}},
    "sizing": {"risk": 0.0075, "notional_cap": 0.20, "weight": 1.0},
}

# momentum-continuation long (momo) — signal_momo(): a clean high-volume 4h
# breakout that closes strong. runup>=12%, vol>=2.5x, upper wick<=15%, close in
# the top 20% of the 4h range; stop from the signal window.
MOMO = {
    "name": "momentum-long",
    "side": "long",
    "market": "crypto_perp",
    "universe": "fleet-60",
    "entry": {"logic": "AND", "children": [
        {"left": {"ind": "ROC", "params": {"period": 16}}, "op": "ge",
         "right": 0.12},
        {"left": {"ind": "VOL_RATIO", "params": {"period": 8}}, "op": "ge",
         "right": 2.5},
        {"left": {"ind": "WICK_FRAC", "params": {"period": 16}}, "op": "le",
         "right": 0.15},
        {"left": {"ind": "CLOSE_POS", "params": {"period": 16}}, "op": "ge",
         "right": 0.80},
    ]},
    "exit": {"time_bars": 48, "stop": {"mode": "sig", "window": 16,
                                       "param": 0.001}},
    "sizing": {"risk": 0.0075, "notional_cap": 0.20, "weight": 1.0},
}

# capitulation long — signal_capit(): 24h drop <= -20% on a fresh crossing
CAPIT = {
    "name": "capit-long",
    "side": "long",
    "market": "crypto_perp",
    "universe": "fleet-60",
    "fresh": True,
    "entry": {"logic": "AND", "children": [
        {"left": {"ind": "ROC", "params": {"period": 96}}, "op": "le",
         "right": -0.2},
    ]},
    "exit": {"time_bars": 96, "stop": {"mode": "none", "param": 0.0}},
    "sizing": {"risk": 0.0075, "notional_cap": 0.20, "weight": 1.0},
}
