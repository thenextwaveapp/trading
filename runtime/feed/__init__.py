"""Feed signal pipeline: raw social/news events -> a per-(instrument, bar-close)
score+confidence series the engine reads via the aux path.

Stages (one module each), deliberately OUTSIDE core/ so the trading engine never
learns what a tweet is:

    resolve   event text        -> [(instrument, resolution_confidence)]
    score     (event, instrument) -> {direction, magnitude, source_conf, class_conf}
    aggregate decayed events    -> continuous score, sampled to bar closes,
                                   with the composite confidence
    service   the loop: pf_social_raw / pf_news -> resolve -> score -> aggregate
              -> upsert pf_feed_score

Ingestion lives in runtime/scan/ (scan/news.py exists; scan/social.py is the X
adapter). This package does the analysis scan deliberately refuses to do.
"""
