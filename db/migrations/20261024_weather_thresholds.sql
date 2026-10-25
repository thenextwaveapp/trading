-- Weather gate: persist the volatility terciles the cells were built from.
-- Without them the live fleet cannot classify today's volatility on the same
-- scale as the backtest, so the gate could not be enforced. Idempotent.
--
--   psql "$DATABASE_URL" -f db/migrations/20261024_weather_thresholds.sql

ALTER TABLE public.pf_conditions
  ADD COLUMN IF NOT EXISTS vol_lo numeric,
  ADD COLUMN IF NOT EXISTS vol_hi numeric;
