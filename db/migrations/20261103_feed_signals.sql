-- db/migrations/20261103_feed_signals.sql
-- Social/news feed signals. Three tables, split by how the data is sourced and
-- how often it is recomputed:
--   pf_social_raw   immutable raw events (tweets/posts), ingested by the scan
--                   layer with NO analysis — the fact, kept verbatim.
--   pf_feed_sources author/outlet credibility priors (source -> weight),
--                   maintained by hand, read by the scoring job.
--   pf_feed_score   the DERIVED per-(instrument, bar-close) series the engine
--                   reads via the aux path. Recomputable from raw as the scorer
--                   and decay params improve, so it is a view over raw, never
--                   overwritten onto it. Carries the decomposed confidence and
--                   the triggering event so each fill can show its provenance.
-- pf_news (crypto headlines) already exists from the news scan; it feeds the
-- same scoring job as a second raw source.

CREATE TABLE IF NOT EXISTS public.pf_social_raw (
    event_id       text PRIMARY KEY,                 -- source-native id (dedup)
    source         text NOT NULL,                    -- 'x', 'reddit', ...
    author_id      text,
    author_handle  text,
    text           text NOT NULL,
    lang           text,
    url            text,
    created_at_ms  bigint NOT NULL,                  -- when it was posted
    ingested_at_ms bigint NOT NULL,                  -- when we received it
    raw            jsonb,                            -- untouched payload
    inserted_at    timestamp with time zone NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pf_social_raw_created_idx
    ON public.pf_social_raw (created_at_ms);

CREATE TABLE IF NOT EXISTS public.pf_feed_sources (
    source_key  text PRIMARY KEY,                    -- e.g. 'x:@binance'
    label       text,
    kind        text NOT NULL DEFAULT 'social',      -- 'social' | 'news'
    credibility double precision NOT NULL DEFAULT 0.5,  -- prior weight [0,1]
    updated_at  timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_feed_score (
    instrument         text NOT NULL,                -- base symbol (e.g. 'BTC')
    kind               text NOT NULL,                -- 'social' | 'news'
    t_close            bigint NOT NULL,              -- bar-close ms (aux key)
    score              double precision NOT NULL,    -- signed/decayed signal
    confidence         double precision NOT NULL,    -- composite [0,1]
    conf_source        double precision,
    conf_resolution    double precision,
    conf_corroboration double precision,
    conf_classification double precision,
    conf_freshness     double precision,
    event_id           text,                         -- triggering event
    event_text         text,
    event_created_ms   bigint,                       -- for the staleness gate
    scored_at_ms       bigint NOT NULL,
    PRIMARY KEY (instrument, kind, t_close)
);
CREATE INDEX IF NOT EXISTS pf_feed_score_inst_kind_t_idx
    ON public.pf_feed_score (instrument, kind, t_close);
