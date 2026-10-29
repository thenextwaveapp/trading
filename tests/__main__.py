"""Run the engine self-tests as one suite:  python -m tests

Each module exposes main() -> 0 (pass) / non-zero (fail). We run them in a
child-safe way, capture their (verbose) output, and print one line per suite —
dumping full output only for failures. Exit code is non-zero if any suite fails.
"""
import contextlib
import importlib
import io
import sys

SUITES = [
    "selftest",             # spec parser vs legacy signal
    "selftest_backtest",    # backtest ledger reproduces legacy trade-for-trade
    "selftest_exit",        # exit logic (stop / tp / time)
    "selftest_momo",        # momentum entry
    "selftest_universe",    # universe resolution from market data
    "selftest_db_universe",  # universe resolution against the DB (mocked)
    "selftest_conditions",   # weather buckets from a trade ledger
    "selftest_worker",       # worker DB write-back + stage transitions
    "selftest_spec_runtime", # DB-fleet exits on the post-signal tape
    "selftest_params",       # typed parameter registry + capability map
    "selftest_timing",       # UTC hour/day signal windows
    "selftest_exits_side",   # side-aware stops + two-sided trailing
    "selftest_service",      # service capability gates before data loading
    "selftest_sweep",        # parameter grid expansion + per-run sweep results
    "selftest_challenges",   # challenge lock-set, predicates, judges
    "selftest_challenge_runner",  # challenge settle loop end-to-end over candles
    "selftest_equity",       # mark-to-market equity curve follows price
]


def run():
    results = {}
    for name in SUITES:
        mod = importlib.import_module(f"tests.{name}")
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = mod.main()
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 0
        except Exception:  # a suite that blew up is a failure, not a crash
            import traceback
            buf.write(traceback.format_exc())
            rc = 1
        ok = (rc == 0)
        results[name] = ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print("  ---- output " + "-" * 50)
            for line in buf.getvalue().splitlines():
                print(f"    {line}")
            print("  " + "-" * 62)

    n_ok = sum(results.values())
    print(f"\n{n_ok}/{len(results)} suites passed")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(run())
