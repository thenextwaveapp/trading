"""Scoring: (event, instrument) -> {direction, magnitude, source_conf, class_conf}.

This is a BASELINE, deliberately simple and deterministic so the pipeline is
testable and reproducible today without a model or API key:

  - direction  signed [-1, 1] from a small finance lexicon (hack/paused/lawsuit
               bearish; approved/listing/partnership bullish);
  - magnitude  [0, 1] from how many strong terms hit (novelty/strength proxy);
  - class_conf [0, 1] confidence in that classification (mixed signals -> low);
  - source_conf credibility prior for the author/outlet, from pf_feed_sources.

Swap-in point: replace `classify()` with a finance-tuned transformer or an LLM
call. Everything downstream (aggregate, the aux series, the engine) is unchanged
— it only ever sees the four numbers.
"""

BEARISH = ("hack", "hacked", "exploit", "drained", "breach", "paused",
           "halt", "halted", "lawsuit", "sue", "sued", "ban", "banned",
           "delist", "delisted", "insolvent", "bankrupt", "down", "outage")
BULLISH = ("approved", "approval", "listing", "listed", "partnership",
           "integrates", "launch", "launched", "upgrade", "buy", "buys",
           "bought", "surges", "record", "adopts", "reserve")

STRONG = ("hack", "exploit", "lawsuit", "approved", "listing", "delisted",
          "bankrupt", "breach")


def classify(text: str):
    """-> (direction[-1,1], magnitude[0,1], class_conf[0,1]). Baseline lexicon."""
    low = (text or "").lower()
    bear = sum(low.count(w) for w in BEARISH)
    bull = sum(low.count(w) for w in BULLISH)
    total = bear + bull
    if total == 0:
        return 0.0, 0.0, 0.0
    direction = (bull - bear) / total
    strong_hits = sum(low.count(w) for w in STRONG)
    magnitude = min(1.0, 0.3 + 0.2 * strong_hits + 0.1 * total)
    # confidence drops when the text is mixed (both bull and bear present)
    mixed = min(bear, bull) / total
    class_conf = max(0.0, 1.0 - 2.0 * mixed)
    return direction, magnitude, class_conf


def score_event(text: str, source_key: str, source_credibility):
    """Full baseline score for one (event text, source). `source_credibility`
    is a callable source_key -> prior [0,1] (default 0.5), typically a lookup
    into pf_feed_sources."""
    direction, magnitude, class_conf = classify(text)
    source_conf = source_credibility(source_key) if source_credibility else 0.5
    return {"direction": direction, "magnitude": magnitude,
            "class_conf": class_conf, "source_conf": source_conf}
