"""Build worker — DB write-back order and stage transitions.

Run: python3 -m tests.selftest_worker
"""
from core.mapping import variant_to_spec
from runtime import engine_worker


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.patches = []
        self.inserts = []

    def enabled(self):
        return True

    def get(self, table, query=""):
        return [dict(r) for r in self.rows.get(table, [])]

    def patch(self, table, query, changes):
        self.patches.append((table, query, changes))
        for row in self.rows.get(table, []):
            if f"id=eq.{row['id']}" in query:
                row.update(changes)

    def insert(self, table, row):
        self.inserts.append((table, row))


def canned_out(passed=True):
    return {
        "ok": True,
        "stats": {"n": 4, "win_rate": 0.5, "net_pct_per_trade": 1.25,
                  "total_net_pct": 5.0, "final_equity": 10500.0,
                  "max_drawdown": -0.03,
                  "equity_curve": [[1, 10000], [2, 10500]]},
        "window": {"start": "2024-01-01", "end": "2026-01-01",
                   "bars": 100, "symbols": 2, "source": "cache"},
        "checks": [{"key": "placebo", "label": "Beats random entries",
                    "passed": passed, "stat": 1.0, "threshold": 0.5}],
        "conditions": [{"volatility": "low", "btc_trend": "rising",
                        "return_per_trade": 1.0, "trades": 4,
                        "is_current": True}],
        "longest_gap_days": 12.0,
        "drawdown_recovery_days": 3.0,
        "error": None,
    }


def run_case(passed):
    bot = {"id": "bot-1", "name": "unit", "spec": {"side": "short",
                                                  "universe": "old",
                                                  "name": "unit"},
           "family_slug": "pump_short", "params": {}, "universe_id": None}
    bt = {"id": "bt-1", "bot_id": "bot-1"}
    db = FakeDB({"pf_bots": [bot], "pf_backtests": [bt]})
    old = engine_worker.pf_db, engine_worker.ep_evaluate
    engine_worker.pf_db = db
    engine_worker.ep_evaluate = lambda body: (200, canned_out(passed))
    try:
        engine_worker.process(bt)
    finally:
        engine_worker.pf_db, engine_worker.ep_evaluate = old

    ok = True
    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    check(bt["status"] == "done", "backtest status should be done")
    check(bot["stage"] == "trials", "bot should land on trials")
    check(bot["spec"]["universe"] == "fleet-60", "spec universe should be persisted")
    check(bot["bt"] == 1.25, "bot edge should be written")
    check(len([r for t, r in db.inserts if t == "pf_checks"]) == 1,
          "one check should be written")
    check(len([r for t, r in db.inserts if t == "pf_conditions"]) == 1,
          "one condition cell should be written")
    patches = [c for t, _q, c in db.patches if t == "pf_backtests"]
    check(any(c.get("status") == "done" for c in patches),
          "done status should be patched")
    check(not any(c.get("status") == "error" for c in patches),
          "passing run must not be marked error")
    result = next(c for c in patches if "longest_gap_days" in c)
    check(isinstance(result["longest_gap_days"], int),
          "longest_gap_days must be an int for the DB")
    check(isinstance(result["drawdown_recovery_days"], int),
          "drawdown_recovery_days must be an int for the DB")
    return ok


def canned_sweep():
    return {
        "ok": True, "count": 2, "completed": 2,
        "window": {"start": "2024-01-01", "end": "2026-01-01"},
        "runs": [
            {"label": "Max hold=5", "changes": {"exit.time_bars": 5},
             "stats": {"n": 4, "net_pct_per_trade": 1.0},
             "issues": [], "error": None},
            {"label": "Max hold=10", "changes": {"exit.time_bars": 10},
             "stats": {"n": 2, "net_pct_per_trade": 0.5},
             "issues": [], "error": "late failure"},
        ],
    }


def check_sweep():
    sweep = {"id": "sw-1", "spec": {"side": "short", "entry": {}},
             "axes": [{"path": "exit.time_bars", "values": [5, 10]}],
             "universe_id": None, "universe_slug": "fleet-60"}
    db = FakeDB({"pf_sweeps": [sweep]})
    old = engine_worker.pf_db, engine_worker.ep_sweep
    engine_worker.pf_db = db
    engine_worker.ep_sweep = lambda body: (200, canned_sweep())
    try:
        engine_worker.process_sweep(sweep)
    finally:
        engine_worker.pf_db, engine_worker.ep_sweep = old

    ok = True
    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("FAIL:", msg)
            ok = False

    check(sweep["status"] == "done", "sweep status should be done")
    check(sweep["run_count"] == 2 and sweep["completed_count"] == 2,
          "sweep should persist its grid counts")
    runs = [r for t, r in db.inserts if t == "pf_sweep_runs"]
    check(len(runs) == 2, "one row per sweep point should be written")
    check(runs[1]["error"] == "late failure",
          "a failed grid point should be stored without failing the sweep")

    failed = {"id": "sw-2", "spec": {}, "axes": [], "universe_slug": None}
    db = FakeDB({"pf_sweeps": [failed]})
    old = engine_worker.pf_db, engine_worker.ep_sweep
    engine_worker.pf_db = db
    engine_worker.ep_sweep = lambda body: (400, {"ok": False, "error": "bad grid"})
    try:
        engine_worker.process_sweep(failed)
    finally:
        engine_worker.pf_db, engine_worker.ep_sweep = old
    check(failed["status"] == "error" and "bad grid" in failed.get("error", ""),
          "a failed sweep should be recorded as error")

    allbad = {"id": "sw-3", "spec": {}, "axes": [], "universe_slug": None}
    db = FakeDB({"pf_sweeps": [allbad]})
    out = {"ok": True, "count": 1, "completed": 0,
           "window": None, "runs": [
               {"label": "Side=both", "changes": {"side": "both"},
                "stats": None, "issues": [{"id": "side.both"}],
                "error": "side both blocked"},
           ]}
    old = engine_worker.pf_db, engine_worker.ep_sweep
    engine_worker.pf_db = db
    engine_worker.ep_sweep = lambda body: (200, out)
    try:
        engine_worker.process_sweep(allbad)
    finally:
        engine_worker.pf_db, engine_worker.ep_sweep = old
    check(allbad["status"] == "error" and "all 1 grid point failed" in allbad.get("error", ""),
          "an all-failed grid should surface as an error")
    check(len([r for t, r in db.inserts if t == "pf_sweep_runs"]) == 1,
          "failed grid rows should still be stored")
    return ok


def check_momo_params():
    """Editable momo knobs must reach the spec, not fall back to constants."""
    spec = variant_to_spec("momo_long", {"runup": 0.2, "vol": 3.0, "hold": 10})
    kids = spec["entry"]["children"]
    return (kids[0]["right"] == 0.2 and kids[1]["right"] == 3.0
            and spec["exit"]["time_bars"] == 10)


def main():
    a = run_case(True)
    b = run_case(False)
    c = check_momo_params()
    d = check_sweep()
    if not c:
        print("FAIL: momo params did not flow into the spec")
    if a and b and c and d:
        print("PASS: worker persists spec, ledger, checks, conditions, stage, and sweeps")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
