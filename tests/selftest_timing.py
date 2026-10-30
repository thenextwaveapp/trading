"""UTC signal windows — close-time hour/day filtering, including fresh.

Run: python3 -m tests.selftest_timing
"""
from datetime import datetime, timezone

from core.evaluator import entry_signal
from core.strategy import parse

M15 = 900_000
T0 = 1704067200000          # Mon 2024-01-01 00:00 UTC
N = 7 * 96

SPEC = {
    "side": "short",
    "entry": {"logic": "AND", "children": [
        {"left": {"ind": "close"}, "op": "gt", "right": 0},
    ]},
    "exit": {"time_bars": 16, "stop": {"mode": "hh", "param": 0.0}},
}


def candles():
    return [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
             "c": 100.0, "v": 10.0} for i in range(N)]


def signals(spec, c):
    strat = parse(spec)
    out = []
    for i in range(len(c)):
        s = entry_signal(strat, c, i)
        if s:
            out.append((i, s))
    return out


def close_dt(t):
    return datetime.fromtimestamp((t + M15) / 1000, tz=timezone.utc)


def main():
    c = candles()
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    all_sigs = signals(SPEC, c)
    check(all_sigs and all_sigs[0][0] == 8,
          "without timing the first valid bar should fire")
    check(len(all_sigs) == N - 8,
          f"without timing every valid bar should fire, got {len(all_sigs)}")

    hours = signals({**SPEC, "timing": {"hours_utc": [3], "days_utc": []}}, c)
    check(hours, "hour window should still produce signals")
    check(all(close_dt(s["t_sig"] - M15).hour == 3 for _, s in hours),
          "every signal must close inside hour 3 UTC")
    check(len(hours) == 7 * 4,
          f"hour 3 has four closes/day; expected 28, got {len(hours)}")

    days = signals({**SPEC, "timing": {"hours_utc": [], "days_utc": [1]}}, c)
    check(days, "day window should still produce signals")
    check(all(close_dt(s["t_sig"] - M15).weekday() == 1 for _, s in days),
          "every signal must close on Tuesday UTC")
    check(len(days) == 96, f"one full Tuesday expected, got {len(days)}")

    combo = signals({**SPEC, "timing": {"hours_utc": [3], "days_utc": [1]}}, c)
    check(len(combo) == 4,
          f"Tuesday hour 3 has four closes; got {len(combo)}")
    check(all(close_dt(s["t_sig"] - M15).weekday() == 1
              and close_dt(s["t_sig"] - M15).hour == 3 for _, s in combo),
          "combined window must satisfy both filters")

    fresh = signals({**SPEC, "fresh": True,
                     "timing": {"hours_utc": [3], "days_utc": []}}, c)
    check(len(fresh) == 7,
          f"fresh should fire once per session, got {len(fresh)}")
    check(all(close_dt(s["t_sig"] - M15).minute == 0
              for _, s in fresh),
          "fresh should fire on the first close of the hour")

    midnight = signals({**SPEC, "timing": {"hours_utc": [0], "days_utc": []}}, c)
    first = midnight[0]
    check(close_dt(first[1]["t_sig"] - M15).hour == 0,
          "23:45 close should belong to UTC hour 0")
    check(first[0] == 95,
          f"23:45 bar index should be 95, got {first[0]}")

    empty = signals({**SPEC, "timing": {"hours_utc": [], "days_utc": []}}, c)
    check(len(empty) == len(all_sigs),
          "empty timing should behave like no timing")

    # one-off calendar dates (measured at bar close, UTC)
    def fired_dates(sigs):
        return sorted({close_dt(s["t_sig"] - M15).date().isoformat()
                       for _, s in sigs})

    one = signals({**SPEC, "timing": {"dates": ["2024-01-03"]}}, c)
    check(len(one) == 96 and fired_dates(one) == ["2024-01-03"],
          f"a single date should fire only that whole UTC day, got {fired_dates(one)}")

    rng = signals({**SPEC, "timing": {"dates": ["2024-01-04/2024-01-06"]}}, c)
    check(fired_dates(rng) == ["2024-01-04", "2024-01-05", "2024-01-06"],
          f"an inclusive range should fire across its days, got {fired_dates(rng)}")

    mixed = signals({**SPEC, "timing":
                     {"dates": ["2024-01-02", "2024-01-05/2024-01-06"]}}, c)
    check(fired_dates(mixed) == ["2024-01-02", "2024-01-05", "2024-01-06"],
          f"single + range should union, got {fired_dates(mixed)}")

    date_hour = signals({**SPEC, "timing":
                         {"dates": ["2024-01-03"], "hours_utc": [3]}}, c)
    check(len(date_hour) == 4 and fired_dates(date_hour) == ["2024-01-03"],
          f"dates AND hours should both apply, got {len(date_hour)}")

    for bad in (["2024-13-01"], ["2024-01-06/2024-01-04"], ["nope"], "x"):
        try:
            parse({**SPEC, "timing": {"dates": bad}})
            check(False, f"bad timing.dates {bad!r} must be rejected")
        except Exception:
            pass

    if ok:
        print(f"PASS: {len(hours)} hour-3, {len(days)} Tuesday, "
              f"{len(fresh)} fresh-session signals; dates/ranges; "
              f"close-time UTC semantics")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
