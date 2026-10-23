"""Seed presets — the founder's frozen rules expressed as compositions.

RULE_P is the pump-short base, RULE_P_WICK adds the wick filter, MOMO is the
momentum-long breakout, and CAPIT is the capitulation long. Each is just a
Strategy; in the product they are entries in the preset gallery.
"""

# pump-short base (Rule P)
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

# pump-short + upper-wick >= 30%
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

# momentum-continuation long: high-volume 4h breakout that closes strong.
# runup>=12%, vol>=2.5x, upper wick<=15%, close in the top 20% of the 4h range;
# stop from the signal window.
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

# capitulation long: 24h drop <= -20% on a fresh crossing
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
