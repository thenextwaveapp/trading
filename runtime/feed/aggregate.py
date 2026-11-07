"""Aggregation: scored events -> a continuous score sampled to bar closes.

Events are sparse and irregular; the engine wants one value per bar. So each
event's contribution decays exponentially (half-life in seconds) and concurrent
events are summed. At each bar close we read the decayed state, producing one
row per (instrument, t_close) with the score and a DECOMPOSED confidence:

    source        credibility prior of the strongest contributing event
    resolution    how sure we mapped the event to this instrument
    corroboration how many independent live events agree (more -> higher)
    classification the NLP's certainty about direction/magnitude
    freshness     position on the decay curve (a fading event is less fresh)

composite confidence = source * resolution * classification, lifted by
corroboration and freshness. All five are stored so a low score is legible
("0.6 because only one account posted it").

The row's `event_ts` is the most recent contributing event's time — the engine's
staleness gate (feed.max_signal_age_sec) measures the bar close against it.
"""
import math


def _decay(dt_s, half_life_s):
    if dt_s < 0:
        return 0.0
    return 0.5 ** (dt_s / half_life_s)


def aggregate(events, bar_closes_ms, half_life_s=300, kind="social"):
    """events: list of dicts, each
         {instrument, t_ms, direction, magnitude, class_conf, source_conf,
          resolution_conf}
       bar_closes_ms: ascending list of bar-close timestamps (ms).
       -> list of rows keyed (instrument, t_close), aux-ready (t, score,
          confidence, event_ts) plus the decomposed confidence components."""
    by_inst = {}
    for e in events:
        by_inst.setdefault(e["instrument"], []).append(e)
    for evs in by_inst.values():
        evs.sort(key=lambda e: e["t_ms"])

    rows = []
    for inst, evs in by_inst.items():
        for t_close in bar_closes_ms:
            live = [e for e in evs if e["t_ms"] <= t_close]
            if not live:
                continue
            score = 0.0
            strongest = None
            best_contrib = -1.0
            last_ts = None
            recent = 0
            for e in live:
                d = _decay((t_close - e["t_ms"]) / 1000.0, half_life_s)
                if d < 0.01:
                    continue
                w = e.get("source_conf", 0.5) * e.get("resolution_conf", 1.0)
                contrib = e["direction"] * e["magnitude"] * w * d
                score += contrib
                recent += 1
                last_ts = e["t_ms"] if last_ts is None else max(last_ts, e["t_ms"])
                if abs(contrib) > best_contrib:
                    best_contrib = abs(contrib)
                    strongest = (e, d)
            if strongest is None:
                continue
            e, d = strongest
            corroboration = 1.0 - math.exp(-recent)          # 1 ev ~0.63, grows
            conf = (e.get("source_conf", 0.5)
                    * e.get("resolution_conf", 1.0)
                    * e.get("class_conf", 0.0))
            conf = min(1.0, conf * (0.6 + 0.4 * corroboration) * (0.5 + 0.5 * d))
            rows.append({
                "instrument": inst, "kind": kind, "t_close": t_close,
                "t": t_close, "score": round(score, 6),
                "confidence": round(conf, 6),
                "conf_source": e.get("source_conf"),
                "conf_resolution": e.get("resolution_conf"),
                "conf_corroboration": round(corroboration, 6),
                "conf_classification": e.get("class_conf"),
                "conf_freshness": round(d, 6),
                "event_ts": last_ts,
            })
    rows.sort(key=lambda r: (r["instrument"], r["t_close"]))
    return rows
