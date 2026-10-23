-- paperfleet RLS policies, one set per table:
--   <table>_rw = owner write (FOR ALL); <table>_read = public/visibility read.
-- Anon-key reads (auth.uid() IS NULL) stay open for public data; writes are owner-scoped.
-- Run after schema.sql. Idempotent: drops any existing pf_* policy first.

DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT policyname, tablename FROM pg_policies
           WHERE schemaname = 'public' AND tablename LIKE 'pf_%'
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', r.policyname, r.tablename);
  END LOOP;
END $$;

-- owner-private (owner ALL; no public read)
CREATE POLICY pf_alert_settings_rw  ON public.pf_alert_settings  FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_api_keys_rw        ON public.pf_api_keys        FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_auth_methods_rw    ON public.pf_auth_methods    FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_bot_defaults_rw    ON public.pf_bot_defaults    FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_invoices_rw        ON public.pf_invoices        FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_payment_methods_rw ON public.pf_payment_methods FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_subscriptions_rw   ON public.pf_subscriptions   FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());

-- owner-write + public read
CREATE POLICY pf_fleets_rw      ON public.pf_fleets    FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_fleets_read    ON public.pf_fleets    FOR SELECT USING (true);
CREATE POLICY pf_universes_rw   ON public.pf_universes FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_universes_read ON public.pf_universes FOR SELECT USING (true);
CREATE POLICY pf_profiles_rw    ON public.pf_profiles  FOR ALL USING (id = auth.uid()) WITH CHECK (id = auth.uid());
CREATE POLICY pf_profiles_read  ON public.pf_profiles  FOR SELECT USING (true);

-- public reference tables (read-only via RLS; writes are service-role)
CREATE POLICY pf_coins_read             ON public.pf_coins             FOR SELECT USING (true);
CREATE POLICY pf_plans_read             ON public.pf_plans             FOR SELECT USING (true);
CREATE POLICY pf_strategy_families_read ON public.pf_strategy_families FOR SELECT USING (true);

-- bots + children (owner writes; read when parent bot is not private)
CREATE POLICY pf_bots_rw   ON public.pf_bots FOR ALL USING (owner = auth.uid()) WITH CHECK (owner = auth.uid());
CREATE POLICY pf_bots_read ON public.pf_bots FOR SELECT USING (visibility <> 'private' OR owner = auth.uid());

CREATE POLICY pf_backtests_rw ON public.pf_backtests FOR ALL
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_backtests.bot_id AND b.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_backtests.bot_id AND b.owner = auth.uid()));
CREATE POLICY pf_backtests_read ON public.pf_backtests FOR SELECT
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_backtests.bot_id AND (b.visibility <> 'private' OR b.owner = auth.uid())));

CREATE POLICY pf_bot_versions_rw ON public.pf_bot_versions FOR ALL
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_bot_versions.bot_id AND b.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_bot_versions.bot_id AND b.owner = auth.uid()));
CREATE POLICY pf_bot_versions_read ON public.pf_bot_versions FOR SELECT
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_bot_versions.bot_id AND (b.visibility <> 'private' OR b.owner = auth.uid())));

CREATE POLICY pf_checks_rw ON public.pf_checks FOR ALL
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_checks.bot_id AND b.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_checks.bot_id AND b.owner = auth.uid()));
CREATE POLICY pf_checks_read ON public.pf_checks FOR SELECT
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_checks.bot_id AND (b.visibility <> 'private' OR b.owner = auth.uid())));

CREATE POLICY pf_conditions_rw ON public.pf_conditions FOR ALL
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_conditions.bot_id AND b.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_conditions.bot_id AND b.owner = auth.uid()));
CREATE POLICY pf_conditions_read ON public.pf_conditions FOR SELECT
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_conditions.bot_id AND (b.visibility <> 'private' OR b.owner = auth.uid())));

CREATE POLICY pf_strategy_conditions_rw ON public.pf_strategy_conditions FOR ALL
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_strategy_conditions.bot_id AND b.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_strategy_conditions.bot_id AND b.owner = auth.uid()));
CREATE POLICY pf_strategy_conditions_read ON public.pf_strategy_conditions FOR SELECT
  USING (EXISTS (SELECT 1 FROM pf_bots b WHERE b.id = pf_strategy_conditions.bot_id AND (b.visibility <> 'private' OR b.owner = auth.uid())));

-- universe children (owner of parent universe writes; public read)
CREATE POLICY pf_universe_coins_rw ON public.pf_universe_coins FOR ALL
  USING (EXISTS (SELECT 1 FROM pf_universes u WHERE u.id = pf_universe_coins.universe_id AND u.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM pf_universes u WHERE u.id = pf_universe_coins.universe_id AND u.owner = auth.uid()));
CREATE POLICY pf_universe_coins_read ON public.pf_universe_coins FOR SELECT USING (true);

CREATE POLICY pf_universe_filters_rw ON public.pf_universe_filters FOR ALL
  USING (EXISTS (SELECT 1 FROM pf_universes u WHERE u.id = pf_universe_filters.universe_id AND u.owner = auth.uid()))
  WITH CHECK (EXISTS (SELECT 1 FROM pf_universes u WHERE u.id = pf_universe_filters.universe_id AND u.owner = auth.uid()));
CREATE POLICY pf_universe_filters_read ON public.pf_universe_filters FOR SELECT USING (true);

-- follows (follower writes; public read) and events (visibility read; service writes)
CREATE POLICY pf_follows_rw   ON public.pf_follows FOR ALL USING (follower = auth.uid()) WITH CHECK (follower = auth.uid());
CREATE POLICY pf_follows_read ON public.pf_follows FOR SELECT USING (true);
CREATE POLICY pf_events_read  ON public.pf_events  FOR SELECT USING (visibility <> 'private' OR actor = auth.uid());
