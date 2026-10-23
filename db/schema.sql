-- paperfleet schema (pf_* tables): snapshot of the Supabase public schema.
-- Apply to a FRESH database, then run policies.sql and functions.sql.
-- Source of truth is the DB; regenerate via the queries in db/README.md.

-- ---- tables ----

CREATE TABLE IF NOT EXISTS public.pf_alert_settings (
    owner uuid NOT NULL,
    topic text,
    on_entry boolean NOT NULL DEFAULT true,
    on_exit boolean NOT NULL DEFAULT true,
    on_loss_limit boolean NOT NULL DEFAULT true,
    on_fleet_error boolean NOT NULL DEFAULT true,
    daily_summary boolean NOT NULL DEFAULT false,
    daily_summary_time time without time zone,
    quiet_enabled boolean NOT NULL DEFAULT false,
    quiet_start time without time zone,
    quiet_end time without time zone,
    weekly_report boolean NOT NULL DEFAULT false,
    report_day text,
    push_enabled boolean NOT NULL DEFAULT false,
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_api_keys (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    owner uuid NOT NULL,
    prefix text NOT NULL,
    type text NOT NULL DEFAULT 'live'::text,
    permissions text NOT NULL DEFAULT 'read_only'::text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    revoked_at timestamp with time zone
);

CREATE TABLE IF NOT EXISTS public.pf_auth_methods (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    owner uuid NOT NULL,
    provider text NOT NULL,
    provider_id text,
    connected_email text,
    verified boolean NOT NULL DEFAULT false,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_backtests (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    bot_id uuid NOT NULL,
    universe_id uuid,
    window_start date,
    window_end date,
    initial_capital numeric NOT NULL DEFAULT 10000,
    final_value numeric,
    total_return numeric,
    trades integer,
    win_rate numeric,
    wins integer,
    losses integer,
    avg_trade numeric,
    net_per_trade numeric,
    max_drawdown numeric,
    drawdown_recovery_days integer,
    longest_gap_days integer,
    spread_vs_standin numeric,
    episodes integer,
    by_year jsonb,
    equity_curve jsonb,
    notable jsonb,
    expectations jsonb,
    cost_note text,
    params jsonb,
    status text NOT NULL DEFAULT 'done'::text,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_bot_defaults (
    owner uuid NOT NULL,
    starting_capital numeric NOT NULL DEFAULT 10000,
    position_size numeric NOT NULL DEFAULT 0.30,
    max_concurrent integer NOT NULL DEFAULT 10,
    stop_loss numeric NOT NULL DEFAULT 0.03,
    take_profit numeric NOT NULL DEFAULT 0.10,
    time_limit_h integer NOT NULL DEFAULT 24,
    drawdown_threshold numeric NOT NULL DEFAULT 0.10,
    pause_duration_h integer NOT NULL DEFAULT 24,
    fill_mode text NOT NULL DEFAULT 'conservative'::text,
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_bot_versions (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    bot_id uuid NOT NULL,
    version integer NOT NULL,
    params jsonb NOT NULL,
    change_note text,
    checks_passed integer,
    checks_total integer,
    fingerprint text,
    status text NOT NULL DEFAULT 'active'::text,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_bots (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    owner uuid,
    fleet_id uuid,
    name text NOT NULL,
    family_slug text,
    universe_id uuid,
    direction text,
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    bt numeric,
    note text,
    visibility text NOT NULL DEFAULT 'results'::text,
    created_at timestamp with time zone DEFAULT now(),
    stage text NOT NULL DEFAULT 'draft'::text,
    slug text,
    description text,
    market text NOT NULL DEFAULT 'crypto'::text,
    version integer NOT NULL DEFAULT 1,
    copied_from uuid,
    condition_filter jsonb,
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    validated_at timestamp with time zone,
    launched_at timestamp with time zone,
    spec jsonb
);
-- stage: draft | training | trials | weather | ready | deployed
-- Editable setup knobs (risk_weight, max_concurrent, enabled, sizing) live in params.

CREATE TABLE IF NOT EXISTS public.pf_checks (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    backtest_id uuid NOT NULL,
    bot_id uuid NOT NULL,
    key text NOT NULL,
    label text,
    status text NOT NULL DEFAULT 'pending'::text,
    stat numeric,
    threshold numeric,
    detail jsonb,
    position integer NOT NULL DEFAULT 0,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_coins (
    symbol text NOT NULL,
    binance_symbol text NOT NULL,
    name text
);

CREATE TABLE IF NOT EXISTS public.pf_conditions (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    backtest_id uuid NOT NULL,
    bot_id uuid NOT NULL,
    volatility text NOT NULL,
    btc_trend text NOT NULL,
    return_per_trade numeric,
    trades integer,
    is_current boolean NOT NULL DEFAULT false,
    selected boolean NOT NULL DEFAULT false,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_events (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    ts timestamp with time zone NOT NULL DEFAULT now(),
    type text NOT NULL,
    bot_id uuid,
    bot_name text,
    market text,
    actor uuid,
    actor_handle text,
    target_builder uuid,
    visibility text NOT NULL DEFAULT 'public'::text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS public.pf_fleets (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    owner uuid,
    name text NOT NULL,
    color text DEFAULT '#3a81d7'::text,
    budget_per_bot numeric DEFAULT 10000,
    created_at timestamp with time zone DEFAULT now(),
    market text NOT NULL DEFAULT 'crypto'::text,
    check_interval_min integer NOT NULL DEFAULT 15,
    status text NOT NULL DEFAULT 'active'::text,
    kill_switch_pct numeric,
    benchmark_pct numeric,
    description text,
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_follows (
    follower uuid NOT NULL,
    builder uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_invoices (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    owner uuid NOT NULL,
    amount numeric NOT NULL,
    currency text NOT NULL DEFAULT 'USD'::text,
    status text NOT NULL DEFAULT 'paid'::text,
    issued_at timestamp with time zone NOT NULL DEFAULT now(),
    url text
);

CREATE TABLE IF NOT EXISTS public.pf_payment_methods (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    owner uuid NOT NULL,
    brand text,
    last4 text,
    billing_email text,
    is_default boolean NOT NULL DEFAULT true,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_plans (
    key text NOT NULL,
    label text NOT NULL,
    price_monthly numeric NOT NULL DEFAULT 0,
    max_bots integer,
    max_fleets integer,
    max_backtests_monthly integer,
    features jsonb,
    position integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public.pf_profiles (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    handle text NOT NULL,
    display_name text,
    avatar_color text DEFAULT '#3a81d7'::text,
    bio text,
    tz text DEFAULT 'UTC'::text,
    currency text DEFAULT 'USD'::text,
    created_at timestamp with time zone DEFAULT now(),
    email text,
    profile_public boolean NOT NULL DEFAULT false,
    bots_on_leaderboard boolean NOT NULL DEFAULT false,
    default_bot_visibility text NOT NULL DEFAULT 'results'::text,
    onboarding_step integer NOT NULL DEFAULT 0,
    onboarding_checklist jsonb NOT NULL DEFAULT '{}'::jsonb,
    onboarded_at timestamp with time zone,
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_strategy_conditions (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    bot_id uuid NOT NULL,
    kind text NOT NULL,
    type text NOT NULL,
    measure text,
    direction text,
    amount numeric,
    timeframe text,
    timing text,
    candles text,
    modifiers jsonb,
    raw text,
    position integer NOT NULL DEFAULT 0,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_strategy_families (
    slug text NOT NULL,
    label text NOT NULL,
    description text,
    direction text,
    engine text,
    thesis text,
    default_params jsonb
);

CREATE TABLE IF NOT EXISTS public.pf_subscriptions (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    owner uuid NOT NULL,
    plan_key text NOT NULL,
    status text NOT NULL DEFAULT 'active'::text,
    renewal_date date,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_universe_coins (
    universe_id uuid NOT NULL,
    coin_symbol text NOT NULL
);

CREATE TABLE IF NOT EXISTS public.pf_universe_filters (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    universe_id uuid NOT NULL,
    type text NOT NULL,
    op text,
    min_val numeric,
    max_val numeric,
    threshold numeric,
    unit text,
    value text,
    position integer NOT NULL DEFAULT 0,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.pf_universes (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    slug text NOT NULL,
    name text NOT NULL,
    description text,
    owner uuid,
    created_at timestamp with time zone DEFAULT now(),
    definition jsonb
);

-- ---- primary keys & uniques ----

ALTER TABLE public.pf_alert_settings      ADD CONSTRAINT pf_alert_settings_pkey PRIMARY KEY (owner);
ALTER TABLE public.pf_api_keys            ADD CONSTRAINT pf_api_keys_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_auth_methods        ADD CONSTRAINT pf_auth_methods_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_backtests           ADD CONSTRAINT pf_backtests_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_bot_defaults        ADD CONSTRAINT pf_bot_defaults_pkey PRIMARY KEY (owner);
ALTER TABLE public.pf_bot_versions        ADD CONSTRAINT pf_bot_versions_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_bot_versions        ADD CONSTRAINT pf_bot_versions_bot_id_version_key UNIQUE (bot_id, version);
ALTER TABLE public.pf_bots                ADD CONSTRAINT pf_bots_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_checks              ADD CONSTRAINT pf_checks_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_checks              ADD CONSTRAINT pf_checks_backtest_id_key_key UNIQUE (backtest_id, key);
ALTER TABLE public.pf_coins               ADD CONSTRAINT pf_coins_pkey PRIMARY KEY (symbol);
ALTER TABLE public.pf_conditions          ADD CONSTRAINT pf_conditions_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_conditions          ADD CONSTRAINT pf_conditions_backtest_id_volatility_btc_trend_key UNIQUE (backtest_id, volatility, btc_trend);
ALTER TABLE public.pf_events              ADD CONSTRAINT pf_events_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_fleets              ADD CONSTRAINT pf_fleets_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_follows             ADD CONSTRAINT pf_follows_pkey PRIMARY KEY (follower, builder);
ALTER TABLE public.pf_invoices            ADD CONSTRAINT pf_invoices_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_payment_methods     ADD CONSTRAINT pf_payment_methods_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_plans               ADD CONSTRAINT pf_plans_pkey PRIMARY KEY (key);
ALTER TABLE public.pf_profiles            ADD CONSTRAINT pf_profiles_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_profiles            ADD CONSTRAINT pf_profiles_handle_key UNIQUE (handle);
ALTER TABLE public.pf_strategy_conditions ADD CONSTRAINT pf_strategy_conditions_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_strategy_families   ADD CONSTRAINT pf_strategy_families_pkey PRIMARY KEY (slug);
ALTER TABLE public.pf_subscriptions       ADD CONSTRAINT pf_subscriptions_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_subscriptions       ADD CONSTRAINT pf_subscriptions_owner_key UNIQUE (owner);
ALTER TABLE public.pf_universe_coins      ADD CONSTRAINT pf_universe_coins_pkey PRIMARY KEY (universe_id, coin_symbol);
ALTER TABLE public.pf_universe_filters    ADD CONSTRAINT pf_universe_filters_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_universes           ADD CONSTRAINT pf_universes_pkey PRIMARY KEY (id);
ALTER TABLE public.pf_universes           ADD CONSTRAINT pf_universes_slug_key UNIQUE (slug);

-- ---- checks ----

ALTER TABLE public.pf_bots                ADD CONSTRAINT pf_bots_stage_chk CHECK (stage IN ('draft','training','trials','weather','ready','deployed'));

-- ---- foreign keys ----
-- pf_profiles.id is the auth.users id (set by handle_new_user); no FK to the auth schema.

ALTER TABLE public.pf_alert_settings      ADD CONSTRAINT pf_alert_settings_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_api_keys            ADD CONSTRAINT pf_api_keys_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_auth_methods        ADD CONSTRAINT pf_auth_methods_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_backtests           ADD CONSTRAINT pf_backtests_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES pf_bots(id) ON DELETE CASCADE;
ALTER TABLE public.pf_backtests           ADD CONSTRAINT pf_backtests_universe_id_fkey FOREIGN KEY (universe_id) REFERENCES pf_universes(id) ON DELETE SET NULL;
ALTER TABLE public.pf_bot_defaults        ADD CONSTRAINT pf_bot_defaults_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_bot_versions        ADD CONSTRAINT pf_bot_versions_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES pf_bots(id) ON DELETE CASCADE;
ALTER TABLE public.pf_bots                ADD CONSTRAINT pf_bots_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_bots                ADD CONSTRAINT pf_bots_fleet_id_fkey FOREIGN KEY (fleet_id) REFERENCES pf_fleets(id) ON DELETE SET NULL;
ALTER TABLE public.pf_bots                ADD CONSTRAINT pf_bots_universe_id_fkey FOREIGN KEY (universe_id) REFERENCES pf_universes(id);
ALTER TABLE public.pf_bots                ADD CONSTRAINT pf_bots_family_slug_fkey FOREIGN KEY (family_slug) REFERENCES pf_strategy_families(slug);
ALTER TABLE public.pf_bots                ADD CONSTRAINT pf_bots_copied_from_fkey FOREIGN KEY (copied_from) REFERENCES pf_bots(id) ON DELETE SET NULL;
ALTER TABLE public.pf_checks              ADD CONSTRAINT pf_checks_backtest_id_fkey FOREIGN KEY (backtest_id) REFERENCES pf_backtests(id) ON DELETE CASCADE;
ALTER TABLE public.pf_checks              ADD CONSTRAINT pf_checks_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES pf_bots(id) ON DELETE CASCADE;
ALTER TABLE public.pf_conditions          ADD CONSTRAINT pf_conditions_backtest_id_fkey FOREIGN KEY (backtest_id) REFERENCES pf_backtests(id) ON DELETE CASCADE;
ALTER TABLE public.pf_conditions          ADD CONSTRAINT pf_conditions_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES pf_bots(id) ON DELETE CASCADE;
ALTER TABLE public.pf_events              ADD CONSTRAINT pf_events_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES pf_bots(id) ON DELETE CASCADE;
ALTER TABLE public.pf_fleets              ADD CONSTRAINT pf_fleets_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_follows             ADD CONSTRAINT pf_follows_follower_fkey FOREIGN KEY (follower) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_follows             ADD CONSTRAINT pf_follows_builder_fkey FOREIGN KEY (builder) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_invoices            ADD CONSTRAINT pf_invoices_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_payment_methods     ADD CONSTRAINT pf_payment_methods_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_strategy_conditions ADD CONSTRAINT pf_strategy_conditions_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES pf_bots(id) ON DELETE CASCADE;
ALTER TABLE public.pf_subscriptions       ADD CONSTRAINT pf_subscriptions_owner_fkey FOREIGN KEY (owner) REFERENCES pf_profiles(id) ON DELETE CASCADE;
ALTER TABLE public.pf_subscriptions       ADD CONSTRAINT pf_subscriptions_plan_key_fkey FOREIGN KEY (plan_key) REFERENCES pf_plans(key);
ALTER TABLE public.pf_universe_coins      ADD CONSTRAINT pf_universe_coins_universe_id_fkey FOREIGN KEY (universe_id) REFERENCES pf_universes(id) ON DELETE CASCADE;
ALTER TABLE public.pf_universe_coins      ADD CONSTRAINT pf_universe_coins_coin_symbol_fkey FOREIGN KEY (coin_symbol) REFERENCES pf_coins(symbol) ON DELETE CASCADE;
ALTER TABLE public.pf_universe_filters    ADD CONSTRAINT pf_universe_filters_universe_id_fkey FOREIGN KEY (universe_id) REFERENCES pf_universes(id) ON DELETE CASCADE;

-- ---- row level security ----
-- Policies are defined in policies.sql (run after this file).

ALTER TABLE public.pf_alert_settings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_api_keys            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_auth_methods        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_backtests           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_bot_defaults        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_bot_versions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_bots                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_checks              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_coins               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_conditions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_events              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_fleets              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_follows             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_invoices            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_payment_methods     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_plans               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_profiles            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_strategy_conditions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_strategy_families   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_subscriptions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_universe_coins      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_universe_filters    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pf_universes           ENABLE ROW LEVEL SECURITY;
