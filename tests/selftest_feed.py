"""Social/news feed operands — the event-driven signal path.

A feed operand ({"feed": "social"|"news", "field": "score"|"confidence"}) reads
an externally-scored series supplied via the aux path, NOT off the candle. This
pins the whole slice:

  - the feed-spec contract: a spec that reads a feed MUST carry a plain-language
    thesis and a hard staleness gate (feed.max_signal_age_sec), and its feed
    kind must be wired on the market;
  - alignment is causal and freshness enforces the staleness gate (a stale
    trigger reads as None and never fires — the "no fucky bot" guarantee);
  - a feed-gated entry fires in a real backtest, and does not when stale;
  - requirements are extracted (_requires_feeds) and the feature is detected;
  - confidence-weighted sizing scales a trade's risk by its trigger confidence.

Run: python3 -m tests.selftest_feed
"""
from core.backtest import DEFAULTS, _conf_factor, backtest, summarize
from core.evaluator import build_feed_aux, feed_confidence
from core.expr import FEED_KEY, eval_node
from core.params import spec_issues
from core.strategy import StrategyError, parse

M15 = 900_000
T0 = 0


def base_candles(n):
    return [{"t": T0 + i * M15, "o": 100.0, "h": 101.0, "l": 99.0,
             "c": 100.0, "v": 10.0} for i in range(n)]


def feed_rows(base, scores, confs, lag_s):
    """One feed row per base bar. `t` sits just inside the bar (so alignment is
    identity and never reads a row timestamped exactly at the close); `event_ts`
    is the source event time, set `lag_s` seconds before the bar close so
    freshness can be driven independently of alignment."""
    rows = []
    for k, c in enumerate(base):
        close = c["t"] + M15
        rows.append({"t": c["t"] + 1, "score": scores[k], "confidence": confs[k],
                     "event_ts": close - lag_s[k] * 1000})
    return rows


CROSS = {"left": {"feed": "social", "field": "score"},
         "op": "crosses_above", "right": 0.8}


def feed_spec(**over):
    spec = {"name": "hack_short", "side": "long", "market": "crypto_perp",
            "timeframe": "15m",
            "thesis": "Go long when social score spikes on a named account.",
            "feed": {"max_signal_age_sec": 90},
            "entry": {"logic": "AND", "children": [
                {"left": {"ind": "close"}, "op": "gt", "right": 0}, CROSS]},
            "exit": {"time_bars": 4, "stop": {"mode": "none"}}}
    spec.update(over)
    return spec


def main():
    ok = True

    def check(c, msg):
        nonlocal ok
        if not c:
            print("FAIL:", msg)
            ok = False

    def raises(fn, needle):
        try:
            fn()
        except StrategyError as e:
            return needle in str(e)
        return False

    n = 40
    base = base_candles(n)
    # score crosses 0.8 at bar 20 (0.5 -> 0.9); confidence 0.7 throughout.
    scores = [0.5] * 20 + [0.9] * (n - 20)
    confs = [0.7] * n
    fresh_lag = [30] * n                       # 30s old at each bar close: fresh
    rows = feed_rows(base, scores, confs, fresh_lag)

    # --- 1. feed-spec contract ---------------------------------------------
    check(parse(feed_spec())["_requires_feeds"] == ["social"],
          "a feed spec must require the 'social' feed")
    check(raises(lambda: parse(feed_spec(thesis="")), "thesis"),
          "a feed spec with no thesis must be rejected")
    check(raises(lambda: parse(feed_spec(feed={})), "max_signal_age_sec"),
          "a feed spec with no staleness gate must be rejected")
    check(raises(lambda: parse(feed_spec(market="fx_spot")), "not wired"),
          "a feed kind not wired on the market must be rejected")
    check(raises(lambda: parse(feed_spec(entry={"logic": "AND", "children": [
        {"left": {"feed": "social", "field": "bogus"}, "op": "gt",
         "right": 0.5}]})), "field"),
          "a bad feed field must be rejected")
    # a non-feed bot is unaffected: no feed requirement, thesis optional
    plain = parse({"name": "p", "side": "long", "market": "crypto_perp",
                   "timeframe": "15m",
                   "entry": {"logic": "AND", "children": [
                       {"left": {"ind": "close"}, "op": "gt", "right": 0}]},
                   "exit": {"time_bars": 4, "stop": {"mode": "none"}}})
    check(plain["_requires_feeds"] == [], "a plain bot requires no feed")

    # --- 2. causal alignment + freshness mask ------------------------------
    aux = build_feed_aux(base, M15, {"social": rows}, 90 * 1000)
    entry = aux[(FEED_KEY, "social")]
    check(entry["align"] == list(range(n)),
          f"feed alignment should be identity here, got {entry['align'][:5]}…")
    check(all(entry["fresh"]), "30s-old events must all read as fresh at 90s gate")
    stale_rows = feed_rows(base, scores, confs,
                           [30] * 20 + [999_999] * (n - 20))
    stale_aux = build_feed_aux(base, M15, {"social": stale_rows}, 90 * 1000)
    sfresh = stale_aux[(FEED_KEY, "social")]["fresh"]
    check(sfresh[19] and not sfresh[20],
          "an event far older than the gate must read as stale")

    # --- 3. the gate shows up in evaluation --------------------------------
    check(eval_node(base, CROSS, 20, {}, aux),
          "fresh score crossing 0.8 at bar 20 must evaluate True")
    check(not eval_node(base, CROSS, 20, {}, stale_aux),
          "a stale trigger must evaluate False (staleness gate)")
    check(not eval_node(base, CROSS, 20, {}, None),
          "no feed series supplied -> operand None -> False (live-safe)")

    # --- 4. end-to-end backtest: fires fresh, skips stale ------------------
    strat = parse(feed_spec())
    r = backtest(strat, base, feed_series={"social": rows})
    check(r["stats"]["n"] == 1, f"feed bot should take one trade, got {r['stats']['n']}")
    check(r["trades"] and r["trades"][0]["t_sig"] == 21 * M15,
          "the entry must fire at the bar the score crosses (bar 20 close)")
    check(r["trades"] and r["trades"][0].get("conf") == 0.7,
          "the trade must carry its trigger confidence")
    r_stale = backtest(strat, base, feed_series={"social": stale_rows})
    check(r_stale["stats"]["n"] == 0,
          "a stale trigger must take no trade even though the score crossed")

    # --- 5. confidence detection + requirement in issues -------------------
    issues = spec_issues(feed_spec(), "live")
    feed_iss = [i for i in issues if i["id"] == "operand.feed"]
    check(feed_iss and not feed_iss[0]["blocking"],
          "a feed operand must be detected live and must not block")

    # --- 6. confidence-weighted sizing -------------------------------------
    check(_conf_factor(None, 0.7) == 1.0, "no scale -> full size")
    check(_conf_factor({"min_conf": 0.5, "full_conf": 0.9}, None) == 1.0,
          "non-feed trade (conf None) -> full size")
    check(_conf_factor({"min_conf": 0.5, "full_conf": 0.9}, 0.3) == 0.0,
          "below min confidence -> zero size")
    check(abs(_conf_factor({"min_conf": 0.5, "full_conf": 0.9}, 0.7) - 0.5) < 1e-9,
          "halfway between min and full -> half size")
    check(_conf_factor({"min_conf": 0.5, "full_conf": 0.9}, 0.95) == 1.0,
          "at/above full confidence -> full size")

    cfg = {"risk": 0.0075, "notional_cap": 0.20, "start_equity": 10_000.0}
    trades = r["trades"]                        # carries conf 0.7, net < 0 (fees)
    full = summarize(trades, cfg)
    scaled = summarize(trades, {**cfg, "confidence_scale":
                                {"min_conf": 0.5, "full_conf": 0.9}})
    check(full["final_equity"] < cfg["start_equity"],
          "flat-price feed trade should lose fees at full size")
    check(scaled["final_equity"] > full["final_equity"],
          "half-size (conf 0.7) must move equity less than full size")

    # confidence_scale also threads through backtest() from the spec
    strat_cs = parse(feed_spec(sizing={"confidence_scale":
                                        {"min_conf": 0.5, "full_conf": 0.9}}))
    r_cs = backtest(strat_cs, base, feed_series={"social": rows})
    check(r_cs["stats"]["final_equity"] > r["stats"]["final_equity"],
          "a spec's sizing.confidence_scale must scale the equity curve")

    # --- 7. feed_confidence helper -----------------------------------------
    check(feed_confidence(aux, 20) == 0.7, "feed_confidence reads the fresh row")
    check(feed_confidence(stale_aux, 20) is None,
          "feed_confidence returns None when the aligned row is stale")
    check(feed_confidence(None, 20) is None, "no aux -> no confidence")

    if ok:
        print("PASS: feed operands enforce the thesis+staleness contract, align "
              "causally, gate on freshness, backtest end-to-end, and size by "
              "confidence.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
