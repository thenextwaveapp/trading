"""Challenge runner end-to-end over inline candles.

Proves the loop: entries -> real engine (ep_backtest) -> judge -> standings,
including a broken entry that cannot run (placed last, ineligible). No DB, no
network — the candles are inline and deterministic.

Run: python3 -m tests.selftest_challenge_runner
"""
from runtime.challenge_runner import _ms, next_status, run_challenge

STEP = 900_000  # 15m in ms


def candles():
    """A rising sawtooth: up two bars, down one — a long momentum entry profits,
    and a stricter threshold trades less often, so the two entries differ."""
    out = []
    price = 100.0
    for i in range(80):
        price *= 1.03 if i % 3 != 2 else 0.99
        o = price / (1.03 if i % 3 != 2 else 0.99)
        hi = max(o, price) * 1.004
        lo = min(o, price) * 0.996
        out.append({"t": i * STEP, "o": round(o, 4), "h": round(hi, 4),
                    "l": round(lo, 4), "c": round(price, 4), "v": 1000.0 + i})
    return out


def _spec(threshold):
    return {
        "name": f"roc>{threshold}", "side": "long", "market": "crypto_perp",
        "timeframe": "15m",
        "entry": {"logic": "AND", "children": [
            {"left": {"ind": "ROC", "params": {"period": 1}}, "op": "gt",
             "right": threshold}]},
        "exit": {"time_bars": 2, "stop": {"mode": "dstop", "param": 0.05}},
    }


def _body(threshold):
    return {"spec": _spec(threshold), "candles_by_ticker": {"TEST": candles()}}


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
            print(f"  FAIL: {msg}")

    # a loose threshold, a strict one, and a broken entry that cannot run
    broken = {"spec": {"name": "broken", "side": "long", "market": "crypto_perp",
                       "timeframe": "15m",
                       "entry": {"logic": "AND", "children": [
                           {"left": {"ind": "NOPE_NOT_AN_INDICATOR"}, "op": "gt",
                            "right": 0}]}},
              "candles_by_ticker": {"TEST": candles()}}
    entries = [
        {"id": "loose", "body": _body(0.0)},
        {"id": "strict", "body": _body(0.02)},
        {"id": "broken", "body": broken},
    ]

    standings = run_challenge(entries, "return")
    board = {s["id"]: s for s in standings}

    check(len(standings) == 3, "every entry produces a standing")
    check(board["broken"]["eligible"] is False and board["broken"]["place"] is None,
          "a broken entry is ineligible and unplaced")
    check(board["loose"]["place"] in (1, 2) and board["strict"]["place"] in (1, 2),
          "both runnable entries are placed")
    check({board["loose"]["place"], board["strict"]["place"]} == {1, 2},
          "the two runnable entries take places 1 and 2")

    places = [s["place"] for s in standings if s["place"] is not None]
    check(places == sorted(places), "standings are returned winner-first")

    winner = next(s for s in standings if s["place"] == 1)
    runner = next(s for s in standings if s["place"] == 2)
    check(winner["score"] >= runner["score"], "place 1 scores >= place 2")
    check(isinstance(winner["total_return"], (int, float)),
          "standings carry the headline return")

    # --- the window machine: open -> sealed -> live -> closed --------------
    ch = {"status": "open",
          "build_close":  "2026-10-02T00:00:00+00:00",
          "market_open":  "2026-10-03T00:00:00+00:00",
          "market_close": "2026-10-06T00:00:00+00:00"}
    during_build = _ms("2026-10-01T12:00:00+00:00")
    after_build = _ms("2026-10-02T12:00:00+00:00")
    after_open = _ms("2026-10-04T00:00:00+00:00")
    after_close = _ms("2026-10-07T00:00:00+00:00")

    check(next_status(ch, during_build) is None, "open stays open during the build window")
    check(next_status(ch, after_build) == "sealed", "open -> sealed at build close")
    check(next_status({**ch, "status": "sealed"}, after_open) == "live",
          "sealed -> live at market open")
    check(next_status({**ch, "status": "live"}, after_close) == "closed",
          "live -> closed at market close")
    check(next_status({**ch, "status": "closed"}, after_close) is None,
          "a closed challenge does not move")

    if ok:
        print(f"PASS: challenge settled end-to-end — "
              f"winner {winner['id']} @ {round(winner['total_return'], 2)}% "
              f"(3 entries, 1 ineligible)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
