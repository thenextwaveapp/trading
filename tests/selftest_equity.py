"""Mark-to-market equity curve follows price through a hold.

Run: python3 -m tests.selftest_equity
"""
from core.equity import mtm_curve


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            ok = False
            print(f"  FAIL: {msg}")

    # one long trade held 1000..1400; price runs up then down, closes +50
    trades = [{"entry_t": 1000, "exit_t": 1400, "ticker": "TEST",
               "side": "long", "entry": 100.0, "notional": 1000.0, "pnl": 50.0}]
    prices = {"TEST": [[1000, 100.0], [1100, 110.0], [1200, 105.0],
                       [1300, 95.0], [1400, 102.0]]}

    curve = mtm_curve(trades, prices, start_equity=10000.0)
    at = {t: eq for t, eq in curve}

    check(at[1000] == 10000.0, f"at entry, equity = start, got {at.get(1000)}")
    check(at[1100] == 10100.0, f"up 10% on 1000 notional -> +100, got {at.get(1100)}")
    check(at[1200] == 10050.0, f"up 5% -> +50, got {at.get(1200)}")
    check(at[1300] == 9950.0, f"down 5% -> -50, got {at.get(1300)}")
    # at exit bar: realized only, no more unrealized
    check(at[1400] == 10050.0, f"exit bar = start + realized pnl, got {at.get(1400)}")

    # the hold is NOT flat — it follows price
    check(len({at[1000], at[1100], at[1200], at[1300]}) > 1,
          "equity must move during the hold, not be flat")

    # no trades -> empty curve (nothing to draw)
    check(mtm_curve([], prices) == [], "no trades -> empty curve")

    if ok:
        print("PASS: equity follows price through the hold, settles at exit")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
