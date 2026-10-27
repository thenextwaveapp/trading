"""Side-aware stops and two-sided trailing exits.

Run: python3 -m tests.selftest_exits_side
"""
from core.backtest import build_position, exit_trade
from core.strategy import parse

M15 = 900_000
T0 = 1_700_000_000_000
TAKER = 0.00045
SLIP = 0.0005
FEE = 2 * TAKER + SLIP

ENTRY = {"logic": "AND", "children": [
    {"left": {"ind": "close"}, "op": "gt", "right": 0},
]}


def flat(n=40, px=100.0, rng=5.0):
    return [{"t": T0 + i * M15, "o": px, "h": px + rng, "l": px - rng,
             "c": px, "v": 10.0} for i in range(n)]


def spec(side, stop, *, trailing=None):
    exit_ = {"time_bars": 10, "stop": stop}
    if trailing:
        exit_["trailing"] = trailing
    return parse({
        "side": side,
        "entry": ENTRY,
        "exit": exit_,
    })


def signal(entry=100.0):
    return {"t_sig": T0 + M15, "entry": entry, "i": 30, "side": -1}


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    c = flat()

    long_hh = build_position(spec("long", {"mode": "hh", "window": 16,
                                           "param": 0.01}), c, 30, signal())
    check(abs(long_hh["stop"] - 95 * 0.99) < 1e-9,
          f"long hh stop should sit below the window low, got {long_hh['stop']}")
    short_hh = build_position(spec("short", {"mode": "hh", "window": 16,
                                             "param": 0.01}), c, 30, signal())
    check(abs(short_hh["stop"] - 105 * 1.01) < 1e-9,
          f"short hh stop should sit above the window high, got {short_hh['stop']}")

    long_d = build_position(spec("long", {"mode": "dstop", "param": 0.05}),
                            c, 30, signal())
    short_d = build_position(spec("short", {"mode": "dstop", "param": 0.05}),
                             c, 30, signal())
    check(abs(long_d["stop"] - 95) < 1e-9,
          f"long dstop should be below entry, got {long_d['stop']}")
    check(abs(short_d["stop"] - 105) < 1e-9,
          f"short dstop should be above entry, got {short_d['stop']}")

    long_sig = build_position(spec("long", {"mode": "sig", "window": 16,
                                            "param": 0.001}), c, 30, signal())
    short_sig = build_position(spec("short", {"mode": "sig", "window": 16,
                                              "param": 0.001}), c, 30, signal())
    check(long_sig["stop"] < 100, "long sig stop should be below entry")
    check(short_sig["stop"] > 100, "short sig stop should be above entry")

    tr = {"k": 3.0, "natr": 24}
    lp = build_position(spec("long", {"mode": "dstop", "param": 0.05},
                             trailing=tr), c, 30, signal())
    sp = build_position(spec("short", {"mode": "dstop", "param": 0.05},
                             trailing=tr), c, 30, signal())
    check(lp.get("trail_k") == 3.0 and lp.get("natr") == 24,
          "long positions must carry the trailing config")
    check(sp.get("trail_k") == 3.0 and sp.get("natr") == 24,
          "short positions must carry the trailing config")

    # long: rise, then fall through the ratcheted stop
    long_c = [
        {"t": T0, "o": 100, "h": 100.1, "l": 99.9, "c": 100, "v": 10},
        {"t": T0 + M15, "o": 100, "h": 101.0, "l": 100.8, "c": 100.9, "v": 10},
        {"t": T0 + 2 * M15, "o": 101, "h": 102.0, "l": 101.8, "c": 101.9, "v": 10},
        {"t": T0 + 3 * M15, "o": 102, "h": 102.0, "l": 100.5, "c": 100.6, "v": 10},
    ]
    lp = {"entry": 100.0, "hold": 10, "side": 1, "stop": 90.0,
          "t_sig": T0, "i": 0, "trail_k": 1.0, "natr": 0.01}
    got = exit_trade(dict(lp), long_c, TAKER, SLIP)
    check(got is not None and got[2] == "sl",
          f"long trailing should stop out, got {got}")
    if got:
        check(abs(got[0] - (100.98 / 100 - 1 - FEE)) < 1e-9,
              f"long trail level should be 100.98, net {got[0]}")

    # no-stop sentinel plus trailing must still create a stop
    lp0 = {**lp, "stop": 0.0}
    got0 = exit_trade(dict(lp0), long_c, TAKER, SLIP)
    check(got0 is not None and got0[2] == "sl",
          f"long no-stop + trailing should stop out, got {got0}")
    if got0:
        check(abs(got0[0] - (100.98 / 100 - 1 - FEE)) < 1e-9,
              f"long no-stop trail should ratchet to 100.98, net {got0[0]}")

    # short mirror: fall, then rise through the ratcheted stop
    short_c = [
        {"t": T0, "o": 100, "h": 100.1, "l": 99.9, "c": 100, "v": 10},
        {"t": T0 + M15, "o": 100, "h": 99.2, "l": 99.0, "c": 99.1, "v": 10},
        {"t": T0 + 2 * M15, "o": 99, "h": 98.2, "l": 98.0, "c": 98.1, "v": 10},
        {"t": T0 + 3 * M15, "o": 98, "h": 99.5, "l": 99.3, "c": 99.4, "v": 10},
    ]
    sp = {"entry": 100.0, "hold": 10, "side": -1, "stop": 110.0,
          "t_sig": T0, "i": 0, "trail_k": 1.0, "natr": 0.01}
    got = exit_trade(dict(sp), short_c, TAKER, SLIP)
    check(got is not None and got[2] == "sl",
          f"short trailing should stop out, got {got}")
    if got:
        check(abs(got[0] - ((1 - 98.98 / 100) - FEE)) < 1e-9,
              f"short trail level should be 98.98, net {got[0]}")

    sp0 = {**sp, "stop": 0.0}
    got0 = exit_trade(dict(sp0), short_c, TAKER, SLIP)
    check(got0 is not None and got0[2] == "sl",
          f"short no-stop + trailing should stop out, got {got0}")

    if ok:
        print("PASS: hh/dstop/sig are side-aware and trailing works long+short")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
