"""Engine service capability gates — blocked specs stop before data loading.

Run: python3 -m tests.selftest_service
"""
from core.params import default_spec, set_path
from core.presets import CAPIT, MOMO, RULE_P, RULE_P_WICK
from core.service import ep_backtest, ep_evaluate, ep_validate

ENTRY = {"logic": "AND", "children": [
    {"left": {"ind": "close"}, "op": "gt", "right": 0},
]}
M15 = 900_000
H1 = 3_600_000
T0 = 1_700_000_000_000


def base_spec():
    return set_path(default_spec(), "entry", ENTRY)


def candles(n=80):
    return [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
             "c": 100.0 + (i % 5), "v": 10.0} for i in range(n)]


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    for name, spec in (("rule_p", RULE_P), ("wick", RULE_P_WICK),
                       ("momo", MOMO), ("capit", CAPIT)):
        code, out = ep_validate({"spec": spec})
        check(code == 200 and out.get("ok") and not out.get("issues"),
              f"preset {name} should validate cleanly, got {out}")

    spec = base_spec()
    for path, value, issue_id in (
        ("exit.stop.mode", "trail", "stop.trail"),
        ("exit.limit", 0.01, "exit.limit"),
    ):
        blocked = set_path(spec, path, value)
        code, out = ep_validate({"spec": blocked})
        check(code == 200 and not out.get("ok"),
              f"{issue_id} should fail validate")
        check(any(i["id"] == issue_id and i["blocking"]
                  for i in out.get("issues", [])),
              f"{issue_id} should be a blocking issue")
        code, out = ep_backtest({"spec": blocked})
        check(code == 400 and not out.get("ok"),
              f"{issue_id} should stop a backtest before loading data")
        check(any(i["id"] == issue_id for i in out.get("issues", [])),
              f"{issue_id} issue should be returned by backtest")

    ec = set_path(spec, "exit.exit_conditions", ENTRY)
    code, out = ep_validate({"spec": ec})
    check(code == 200 and out.get("ok"),
          f"exit conditions should validate as executable, got {out}")
    code, out = ep_backtest({"spec": ec, "candles": candles()})
    check(code == 200 and out.get("ok"),
          f"exit conditions should run in a backtest, got {out.get('error')}")

    both = set_path(set_path(set_path(spec, "side", "both"),
                             "entry_long", ENTRY), "entry_short", ENTRY)
    code, out = ep_validate({"spec": both})
    check(code == 200 and out.get("ok"),
          f"a well-formed two-sided bot should validate, got {out}")
    code, out = ep_backtest({"spec": both, "candles": candles()})
    check(code == 200 and out.get("ok"),
          f"a two-sided bot should run a backtest, got {out.get('error')}")

    filtered = set_path(spec, "filters", [{"kind": "btc_bear"}])
    code, out = ep_validate({"spec": filtered})
    check(code == 200 and out.get("ok"), "live filters should not block training")
    check(any(i["id"] == "filters" and not i["blocking"]
              for i in out.get("issues", [])),
          "live filters should come back as a warning")

    body = {"spec": spec, "candles": candles()}
    code, out = ep_backtest(body)
    check(code == 200 and out.get("ok") and out["stats"]["n"] > 0,
          f"an executable spec should still run, got {out.get('error')}")
    code, out = ep_evaluate(body)
    check(code == 200 and out.get("ok") and "checks" in out,
          f"evaluate should run on the same tape, got {out.get('error')}")

    h1_spec = set_path(spec, "timeframe", "1h")
    h1 = [{"t": T0 + i * H1, "o": 100.0, "h": 101.0, "l": 99.0,
           "c": 100.0 + (i % 5), "v": 10.0} for i in range(80)]
    code, out = ep_validate({"spec": h1_spec})
    check(code == 200 and out.get("timeframe") == "1h",
          "validate should report the selected candle size")
    code, out = ep_backtest({"spec": h1_spec, "candles": h1})
    check(code == 200 and out.get("ok") and out["stats"]["n"] > 0,
          f"1h inline backtest should run, got {out.get('error')}")

    code, out = ep_backtest({"spec": set_path(spec, "timeframe", "1M"),
                             "candles": h1})
    check(code == 400 and not out.get("ok"),
          "an unsupported candle size must fail before data loading")

    if ok:
        print("PASS: presets validate; blocking issues stop every run entry point")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
