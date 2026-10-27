"""Studio build worker — trains, trials, sweeps and maps a user's bot.

The web enqueues work by inserting a pf_backtests or pf_sweeps row with
status='pending'. This worker drains those rows and runs each through the same
core/ engine the lab and live fleet use (core.service) for backtest<->live
parity, then writes results back to the DB (the single source of truth the web
reads). The web never calls the engine directly.

    pending pf_backtests
        -> ep_evaluate (candles -> backtest + trials + weather)
        -> pf_backtests / pf_checks / pf_conditions / pf_bots.spec
        -> stage 'trials' (or 'draft' on error) -> web

    pending pf_sweeps
        -> ep_sweep (one backtest per grid point, shared candle tape)
        -> pf_sweep_runs -> pf_sweeps status/done

Run:  python -m runtime.engine_worker            # poll loop
      python -m runtime.engine_worker --once     # drain once and exit

Env:  SUPABASE_URL, SUPABASE_SERVICE_KEY (required)
      BUILD_TRAIN_DAYS  training window (default 730 days)
      PAPERFLEET_CANDLE_CACHE  optional bn/ cache directory (default lab/bn)
"""
import os
import sys
import time
from datetime import datetime, timezone

from core.service import ep_evaluate, ep_map, ep_sweep
from . import pf_db

POLL_SECONDS = 10
TRAIN_DAYS = int(os.environ.get("BUILD_TRAIN_DAYS", "730"))
DAY_MS = 86_400_000


def _spec_for(bot: dict, universe_slug: str):
    """The bot's canonical spec. pf_bots.spec is the source of truth; until it's
    backfilled, derive it from family+params via the engine's weld (ep_map),
    the same derivation used everywhere."""
    if bot.get("spec"):
        spec = dict(bot["spec"])
    else:
        code, out = ep_map({
            "family": bot.get("family_slug"),
            "params": bot.get("params") or {},
            "name": bot.get("name", ""),
        })
        if code != 200 or not out.get("ok"):
            raise ValueError(out.get("error", "cannot derive a spec for this bot"))
        spec = out["spec"]
    if spec.get("engine"):
        raise ValueError(
            f"the {spec['engine']} family is engine-specific and can't train in Build yet")
    # The spec is what the live fleet runs; make its universe match the bot.
    spec["universe"] = universe_slug
    spec["name"] = bot.get("name") or spec.get("name", "")
    return spec


def _universe_slug(bot: dict):
    uid = bot.get("universe_id")
    if not uid:
        return "fleet-60"
    rows = pf_db.get("pf_universes", f"id=eq.{uid}&select=slug")
    return rows[0]["slug"] if rows else "fleet-60"


def _window():
    end = int(time.time() * 1000)
    return {"start": end - TRAIN_DAYS * DAY_MS, "end": end}


def _whole_days(x):
    """The DB stores gap/recovery days as integers; the engine reports 1dp."""
    return None if x is None else round(x)


def _cost_note(out: dict):
    w = out.get("window") or {}
    bits = []
    if w.get("start") and w.get("end"):
        bits.append(f"{w['start']} to {w['end']}")
    if w.get("symbols"):
        bits.append(f"{w['symbols']} symbols")
    if w.get("source"):
        bits.append(f"data: {w['source']}")
    bits.append("taker fees + slippage")
    return " · ".join(bits)


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
    pf_db.patch("pf_bots", f"id=eq.{bot['id']}", {"stage": "training"})

    try:
        universe_slug = _universe_slug(bot)
        spec = _spec_for(bot, universe_slug)
        # Persist the derived spec: Deploy and the live runtime read it.
        pf_db.patch("pf_bots", f"id=eq.{bot['id']}", {"spec": spec})

        body = {"spec": spec, "universe": universe_slug, "window": _window()}
        code, out = ep_evaluate(body)
        if code != 200 or not out.get("ok"):
            raise ValueError(out.get("error", "evaluation failed"))

        st = out["stats"]
        w = out.get("window") or {}
        n = st["n"]
        wr = st["win_rate"]
        wins = round(wr * n)
        npt = round(st["net_pct_per_trade"], 4)

        pf_db.patch("pf_backtests", f"id=eq.{bt['id']}", {
            "status": "running",
            "window_start": w.get("start") or None,
            "window_end": w.get("end") or None,
            "initial_capital": 10_000,
            "trades": n,
            "win_rate": round(wr, 4),
            "wins": wins,
            "losses": n - wins,
            "net_per_trade": npt,
            "avg_trade": npt,
            "total_return": round(st["total_net_pct"], 4),
            "final_value": st["final_equity"],
            "max_drawdown": st["max_drawdown"],
            "drawdown_recovery_days": _whole_days(out.get("drawdown_recovery_days")),
            "longest_gap_days": _whole_days(out.get("longest_gap_days")),
            "equity_curve": st["equity_curve"],
            "params": spec,
            "cost_note": _cost_note(out),
        })

        for i, c in enumerate(out.get("checks") or []):
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

        for c in out.get("conditions") or []:
            pf_db.insert("pf_conditions", {
                "backtest_id": bt["id"],
                "bot_id": bot["id"],
                "volatility": c["volatility"],
                "btc_trend": c["btc_trend"],
                "return_per_trade": c.get("return_per_trade"),
                "trades": c.get("trades", 0),
                "vol_lo": c.get("vol_lo"),
                "vol_hi": c.get("vol_hi"),
                "is_current": bool(c.get("is_current")),
            })

        # Every run lands on Trials. Trials are advisory, so the worker does
        # not stop the ladder when a check fails; Weather decides the gate.
        pf_db.patch("pf_bots", f"id=eq.{bot['id']}", {
            "stage": "trials",
            "bt": npt,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        })
        pf_db.patch("pf_backtests", f"id=eq.{bt['id']}", {"status": "done"})
    except Exception as e:  # record a failed run as a result, not a crash
        pf_db.patch("pf_backtests", f"id=eq.{bt['id']}",
                    {"status": "error", "cost_note": str(e)[:500]})
        pf_db.patch("pf_bots", f"id=eq.{bot['id']}", {"stage": "draft"})


def drain() -> int:
    pending = pf_db.get(
        "pf_backtests", "status=eq.pending&select=id,bot_id&order=created_at.asc")
    for bt in pending:
        process(bt)
    return len(pending)


def _sweep_body(sweep: dict):
    spec = dict(sweep.get("spec") or {})
    slug = sweep.get("universe_slug") or spec.get("universe")
    body = {"spec": spec, "axes": sweep.get("axes") or [], "window": _window()}
    if slug:
        body["universe"] = slug
    return body


def process_sweep(sweep: dict):
    """Run one queued sweep; every grid point lands in pf_sweep_runs."""
    now = datetime.now(timezone.utc).isoformat()
    pf_db.patch("pf_sweeps", f"id=eq.{sweep['id']}",
                {"status": "running", "updated_at": now})
    try:
        code, out = ep_sweep(_sweep_body(sweep))
        if code != 200 or not out.get("ok"):
            raise ValueError(out.get("error", "sweep failed"))
        runs = out.get("runs") or []
        for i, run in enumerate(runs):
            pf_db.insert("pf_sweep_runs", {
                "sweep_id": sweep["id"],
                "position": i,
                "label": run.get("label") or f"run {i + 1}",
                "changes": run.get("changes") or {},
                "stats": run.get("stats"),
                "issues": run.get("issues"),
                "error": run.get("error"),
            })
        w = out.get("window") or {}
        success = int(out.get("completed") or 0)
        plural = "" if len(runs) == 1 else "s"
        pf_db.patch("pf_sweeps", f"id=eq.{sweep['id']}", {
            "status": "done" if success else "error",
            "error": None if success else (
                f"all {len(runs)} grid point{plural} failed"),
            "run_count": int(out.get("count") or len(runs)),
            "completed_count": len(runs),
            "window_start": w.get("start") or None,
            "window_end": w.get("end") or None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:  # one bad sweep must not stop the worker
        pf_db.patch("pf_sweeps", f"id=eq.{sweep['id']}", {
            "status": "error",
            "error": str(e)[:500],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })


def drain_sweeps() -> int:
    pending = pf_db.get(
        "pf_sweeps",
        "status=eq.pending&select=id,spec,axes,universe_id,universe_slug"
        "&order=created_at.asc")
    for sweep in pending:
        process_sweep(sweep)
    return len(pending)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not pf_db.enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    once = "--once" in argv
    while True:
        n = m = 0
        try:
            n = drain()
        except Exception as e:
            print(f"backtest worker error: {e}", file=sys.stderr)
        try:
            m = drain_sweeps()
        except Exception as e:
            print(f"sweep worker error: {e}", file=sys.stderr)
        if once:
            print(f"drained {n} pending backtest(s), {m} sweep(s)")
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
