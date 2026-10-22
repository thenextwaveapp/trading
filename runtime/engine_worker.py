"""Studio backtest worker — the one thing that runs a user's backtest.

The web enqueues work by inserting a pf_backtests row with status='pending'
(Studio's "Run backtest"). This worker drains those rows and runs each through
the SAME core/ engine the lab and live fleet use (core.service) — so
backtest<->live parity holds — then writes the results back to the DB, the
single source of truth the web reads. The web never calls the engine directly.

    pending pf_backtests  ->  core.service.ep_backtest / ep_checks  ->  DB  ->  web

Run:  python -m runtime.engine_worker            # poll loop (the service)
      python -m runtime.engine_worker --once     # drain once and exit (cron/tests)
"""
import sys
import time

from core.service import ep_backtest, ep_checks, ep_map
from . import pf_db

POLL_SECONDS = 10


def _spec_for(bot: dict):
    """The bot's canonical spec. pf_bots.spec is the source of truth; until it's
    backfilled, derive it from family+params via the engine's own weld (ep_map)
    — the same derivation used everywhere, not a worker-local shortcut."""
    if bot.get("spec"):
        return bot["spec"]
    code, out = ep_map({
        "family": bot.get("family_slug"),
        "params": bot.get("params") or {},
        "name": bot.get("name", ""),
    })
    if code != 200 or not out.get("ok"):
        raise ValueError(out.get("error", "cannot derive a spec for this bot"))
    return out["spec"]


def _universe_slug(bot: dict):
    uid = bot.get("universe_id")
    if not uid:
        return None
    rows = pf_db.get("pf_universes", f"id=eq.{uid}&select=slug")
    return rows[0]["slug"] if rows else None


def process(bt: dict):
    """Run one pending backtest to completion, writing results + checks."""
    bots = pf_db.get(
        "pf_bots",
        f"id=eq.{bt['bot_id']}&select=id,name,spec,family_slug,params,universe_id")
    if not bots:
        pf_db.patch("pf_backtests", f"id=eq.{bt['id']}",
                    {"status": "error", "cost_note": "bot not found"})
        return
    bot = bots[0]
    pf_db.patch("pf_backtests", f"id=eq.{bt['id']}", {"status": "running"})
    pf_db.patch("pf_bots", f"id=eq.{bot['id']}", {"stage": "backtesting"})

    try:
        body = {"spec": _spec_for(bot), "universe": _universe_slug(bot)}

        code, out = ep_backtest(body)
        if code != 200 or not out.get("ok"):
            raise ValueError(out.get("error", "backtest failed"))
        st = out["stats"]
        n = st["n"]
        wr = st["win_rate"]
        wins = round(wr * n)
        npt = round(st["net_pct_per_trade"], 4)
        pf_db.patch("pf_backtests", f"id=eq.{bt['id']}", {
            "status": "done",
            "trades": n,
            "win_rate": round(wr, 4),
            "wins": wins,
            "losses": n - wins,
            "net_per_trade": npt,
            "avg_trade": npt,
            "total_return": round(st["total_net_pct"], 4),
            "final_value": st["final_equity"],
            "max_drawdown": st["max_drawdown"],
            "equity_curve": st["equity_curve"],
        })

        # the honesty battery -> pf_checks
        ccode, cout = ep_checks(body)
        if ccode == 200 and cout.get("ok"):
            for i, c in enumerate(cout["checks"]):
                pf_db.insert("pf_checks", {
                    "backtest_id": bt["id"],
                    "bot_id": bot["id"],
                    "key": c.get("key", f"check_{i}"),
                    "label": c.get("label"),
                    "status": "pass" if c.get("passed") else "fail",
                    "stat": c.get("stat"),
                    "threshold": c.get("threshold"),
                    "detail": c,
                    "position": i,
                })

        pf_db.patch("pf_bots", f"id=eq.{bot['id']}",
                    {"stage": "validation", "bt": npt})
    except Exception as e:  # a failed run is a result, not a crash — record it
        pf_db.patch("pf_backtests", f"id=eq.{bt['id']}",
                    {"status": "error", "cost_note": str(e)[:500]})
        pf_db.patch("pf_bots", f"id=eq.{bot['id']}", {"stage": "draft"})


def drain() -> int:
    pending = pf_db.get(
        "pf_backtests", "status=eq.pending&select=id,bot_id&order=created_at.asc")
    for bt in pending:
        process(bt)
    return len(pending)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not pf_db.enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    once = "--once" in argv
    while True:
        try:
            n = drain()
            if once:
                print(f"drained {n} pending backtest(s)")
                return 0
        except Exception as e:
            print(f"worker error: {e}", file=sys.stderr)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
