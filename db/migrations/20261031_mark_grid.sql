-- db/migrations/20261031_mark_grid.sql
-- Live equity marks now sit on the candle grid (snapped to 15m, one row per bar
-- and upserted intra-bar) instead of arbitrary wall-clock cycle times, so the
-- curve's time axis is clean — the same grid backfill_curves already writes on.
-- Add the (bot_id, t) uniqueness the upsert targets. Existing per-minute marks
-- have distinct t, so this applies without conflict; run backfill_curves to
-- regularize history onto the grid.
ALTER TABLE public.pf_bot_marks
  ADD CONSTRAINT pf_bot_marks_bot_t_key UNIQUE (bot_id, t);
