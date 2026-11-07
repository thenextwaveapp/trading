-- Paid subscriptions: 7-day trial → $27/mo "pro", via Stripe.
--
-- Stripe is the source of truth; we mirror its state into pf_subscriptions so
-- the app can gate on a local read (owner-only RLS, already in place) instead of
-- calling Stripe per request. The stripe-webhook edge function (service role,
-- bypasses RLS) is the only writer of the mirror fields; the client only reads.
--
-- pf_subscriptions is one-per-owner (unique owner) and already has plan_key,
-- status, renewal_date. We add the Stripe identifiers + period/trial timestamps
-- the mirror needs. pf_profiles gets the customer id (1:1 with the user) so the
-- webhook can map a Stripe customer back to an owner. Everything is additive and
-- idempotent.

-- 1. Stripe customer lives on the profile (one customer per user).
alter table public.pf_profiles
  add column if not exists stripe_customer_id text;

create unique index if not exists pf_profiles_stripe_customer_id_key
  on public.pf_profiles (stripe_customer_id)
  where stripe_customer_id is not null;

-- 2. Mirror fields on the subscription. status/plan_key/renewal_date exist; add
--    the Stripe handles, the trial end, the current period end, and whether the
--    sub is set to cancel at period end (so the UI can say "active until …").
alter table public.pf_subscriptions
  add column if not exists stripe_subscription_id text,
  add column if not exists trial_ends_at          timestamp with time zone,
  add column if not exists current_period_end      timestamp with time zone,
  add column if not exists cancel_at_period_end     boolean not null default false,
  add column if not exists updated_at               timestamp with time zone not null default now();

create index if not exists pf_subscriptions_stripe_subscription_id_idx
  on public.pf_subscriptions (stripe_subscription_id);

-- status mirrors Stripe's subscription.status lexicon. Constrain to the set the
-- app understands so a bad webhook can't write garbage the gate then misreads.
alter table public.pf_subscriptions
  drop constraint if exists pf_subscriptions_status_chk;
alter table public.pf_subscriptions
  add constraint pf_subscriptions_status_chk
  check (status in (
    'trialing', 'active', 'past_due', 'canceled',
    'incomplete', 'incomplete_expired', 'unpaid', 'paused'
  ));

-- 3. Seed the two plans. Free is the implicit no-subscription state; pro is the
--    single paid tier. Reference data (pf_plans) isn't in schema.sql, so it's
--    seeded here. Re-runnable via upsert.
insert into public.pf_plans (key, label, price_monthly, max_bots, max_fleets, max_backtests_monthly, features, position)
values
  ('free', 'Free',  0,  null, 1, null, '{"live": false}'::jsonb, 0),
  ('pro',  'Pro',  27,  null, null, null,
     '{"live": false, "full_access": true, "trial_days": 7}'::jsonb, 1)
on conflict (key) do update set
  label = excluded.label,
  price_monthly = excluded.price_monthly,
  max_fleets = excluded.max_fleets,
  features = excluded.features,
  position = excluded.position;

-- 4. Lock down writes. The owner-only FOR ALL policy would let a client insert
--    its own {status:'active'} row and forge entitlement. The mirror is written
--    ONLY by the stripe-webhook (service role, bypasses RLS), so clients get
--    SELECT only.
drop policy if exists pf_subscriptions_rw   on public.pf_subscriptions;
drop policy if exists pf_subscriptions_read on public.pf_subscriptions;
create policy pf_subscriptions_read on public.pf_subscriptions
  for select using (owner = auth.uid());
