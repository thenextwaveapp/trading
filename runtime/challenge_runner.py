"""Challenge runner — the end-to-end loop that settles a Challenge.

A Challenge is just a set of entered bots (pf_bots with the same challenge_id).
Settling one runs every entry through the *same* core engine over the
Challenge's market window, judges the field, writes the standings, unseals the
entries (results -> public), and closes the Challenge.

    entries ──ep_backtest over [market_open, market_close]──▶ results
            ──core.challenges.rank(judge)──▶ standings
            ──write pf_challenge_standings, unseal, status 'closed'

Same engine as Build and the live Fleet, so a Challenge result is the same kind
of verified record as everything else. INTEGRITY: results come only from this
run over the real window — never from a client.

Run:  python -m runtime.challenge_runner            # poll loop
      python -m runtime.challenge_runner --once     # settle what is due, exit
"""
import sys
import time
from datetime import datetime, timezone

from core.challenges import rank
from core.service import ep_backtest
from . import pf_db

POLL_SECONDS = 30


def _ms(ts):
    """timestamptz (ISO string) -> ms epoch, or None."""
    if not ts:
        return None
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)


def _entry_body(bot, window):
    """An ep_backtest body for one entry: its spec over the market window."""
    spec = bot.get("spec") or {}
    body = {"spec": spec}
    uni = spec.get("universe")
    if uni:
        body["universe"] = uni
    if window:
        body["window"] = window
    return body


def run_challenge(entries, judge, judge_cfg=None):
    """Run + judge a field. `entries` = [{id, body}] where body is an
    ep_backtest body. Returns standings (winner first; failed/ineligible last).
    Pure compute — no DB — so it is testable offline with inline candles."""
    ran, failed, results = [], [], {}
    for e in entries:
        code, out = ep_backtest(e["body"])
        if code == 200 and out.get("ok"):
            results[e["id"]] = {"stats": out["stats"], "trades": out.get("trades") or []}
            ran.append({"id": e["id"], "result": results[e["id"]]})
        else:
            failed.append(e["id"])

    standings = rank(ran, judge, judge_cfg or {})
    for st in standings:
        s = results[st["id"]]["stats"]
        st["trades"] = s.get("n")
        st["total_return"] = s.get("total_net_pct")
        st["max_drawdown"] = s.get("max_drawdown")
    for bid in failed:  # a run that would not execute cannot place
        standings.append({"id": bid, "eligible": False, "place": None,
                          "score": None, "trades": None,
                          "total_return": None, "max_drawdown": None})
    return standings


def settle(challenge):
    """Settle one Challenge end to end against the DB."""
    cid = challenge["id"]
    window = None
    if challenge.get("market_open") and challenge.get("market_close"):
        window = {"start": _ms(challenge["market_open"]),
                  "end": _ms(challenge["market_close"])}

    bots = pf_db.get("pf_bots", f"challenge_id=eq.{cid}&select=id,spec")
    if not bots:
        pf_db.patch("pf_challenges", f"id=eq.{cid}",
                    {"status": "closed", "updated_at": _now()})
        return 0

    entries = [{"id": b["id"], "body": _entry_body(b, window)} for b in bots]
    standings = run_challenge(entries, challenge.get("judge", "return"),
                              challenge.get("judge_cfg") or {})

    for st in standings:
        pf_db.insert("pf_challenge_standings", {
            "challenge_id": cid,
            "bot_id": st["id"],
            "place": st.get("place"),
            "eligible": bool(st.get("eligible")),
            "score": st.get("score"),
            "total_return": st.get("total_return"),
            "max_drawdown": st.get("max_drawdown"),
            "trades": st.get("trades"),
        })

    # unseal: the recipe becomes public now that the window has closed
    for b in bots:
        pf_db.patch("pf_bots", f"id=eq.{b['id']}",
                    {"visibility": "public", "sealed_until": None})
    pf_db.patch("pf_challenges", f"id=eq.{cid}",
                {"status": "closed", "updated_at": _now()})
    return len(standings)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _now_ms():
    return int(time.time() * 1000)


def next_status(ch, now_ms):
    """The status a Challenge should move to at `now_ms`, or None if it stays
    put. Pure so the window machine is testable without a clock or a DB.

        open  --build_close-->  sealed  --market_open-->  live  --market_close-->  closed
    """
    status = ch.get("status")
    if status not in ("open", "sealed", "live"):
        return None
    bc, mo, mc = (_ms(ch.get("build_close")), _ms(ch.get("market_open")),
                  _ms(ch.get("market_close")))
    if mc and now_ms >= mc:
        return "closed"                                   # settle() handles it
    if mo and now_ms >= mo and status in ("open", "sealed"):
        return "live"
    if bc and now_ms >= bc and status == "open":
        return "sealed"
    return None


def advance():
    """Flip Challenges across their build/market windows. Sealing an entry hides
    its Setup (results) until the market window closes; settling (status
    'closed') is left to drain()."""
    rows = pf_db.get(
        "pf_challenges",
        "status=in.(open,sealed,live)"
        "&select=id,status,build_close,market_open,market_close")
    now = _now_ms()
    moved = 0
    for ch in rows:
        tgt = next_status(ch, now)
        if tgt is None or tgt == "closed":
            continue
        pf_db.patch("pf_challenges", f"id=eq.{ch['id']}",
                    {"status": tgt, "updated_at": _now()})
        if tgt == "sealed":  # seal the field: record shown, Setup hidden
            pf_db.patch("pf_bots", f"challenge_id=eq.{ch['id']}",
                        {"visibility": "results",
                         "sealed_until": ch.get("market_close")})
        moved += 1
    return moved


def drain():
    """Settle every Challenge whose market window has closed."""
    due = pf_db.get(
        "pf_challenges",
        "status=in.(sealed,live)"
        f"&market_close=lte.{_now()}"
        "&select=id,judge,judge_cfg,market_open,market_close")
    for ch in due:
        try:
            n = settle(ch)
            print(f"settled challenge {ch['id']}: {n} standings")
        except Exception as e:  # one bad challenge must not stop the runner
            print(f"challenge {ch['id']} error: {e}", file=sys.stderr)
    return len(due)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not pf_db.enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    once = "--once" in argv
    while True:
        moved = n = 0
        try:
            moved = advance()        # open -> sealed -> live across the windows
            n = drain()              # settle anything past its market close
        except Exception as e:
            print(f"challenge runner error: {e}", file=sys.stderr)
        if once:
            print(f"advanced {moved} challenge(s), settled {n}")
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
