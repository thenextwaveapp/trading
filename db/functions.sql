-- paperfleet trigger functions. Run after schema.sql.

-- On auth signup: create the profile, a starter fleet, and bot defaults.
-- Idempotent (ON CONFLICT DO NOTHING) so a pre-seeded account is left intact —
-- this is why the founder's bots are just an ordinary seeded account, not a
-- special case: signup for anyone produces the same shape.
CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  base text;
  h text;
  colors text[] := array['#3a81d7','#3ddc97','#ff5c6c','#d29922','#bc8cff','#39c5cf','#ff7b72','#ffa657'];
  col text;
begin
  base := lower(regexp_replace(split_part(coalesce(new.email,''), '@', 1), '[^a-z0-9]', '', 'g'));
  if base = '' then base := 'user'; end if;
  h := base;
  while exists (select 1 from pf_profiles where handle = h) loop
    h := base || floor(random() * 100000)::text;
  end loop;
  col := colors[1 + (abs(hashtext(new.id::text)) % array_length(colors, 1))];

  -- idempotent: an existing profile (e.g. a seeded account) is left intact
  insert into pf_profiles (id, handle, email, avatar_color, profile_public,
                           bots_on_leaderboard, default_bot_visibility,
                           onboarding_step, onboarding_checklist)
  values (new.id, h, new.email, col, true, true, 'results', 0, '{}'::jsonb)
  on conflict (id) do nothing;

  -- starter fleet only if the user doesn't already have one
  if not exists (select 1 from pf_fleets where owner = new.id) then
    begin
      insert into pf_fleets (owner, name, color, budget_per_bot, market,
                             check_interval_min, status, kill_switch_pct, benchmark_pct)
      values (new.id, 'My Fleet', col, 10000, 'crypto', 15, 'active', -5, 2);
    exception when others then null;
    end;
  end if;

  begin
    insert into pf_bot_defaults (owner, starting_capital, max_concurrent,
                                 time_limit_h, drawdown_threshold, pause_duration_h, fill_mode)
    values (new.id, 10000, 6, 4, -0.05, 72, 'taker')
    on conflict do nothing;
  exception when others then null;
  end;

  return new;
end;
$function$;

-- Trigger on the Supabase auth schema (not dumped by the pf_* queries — standard
-- Supabase signup hook). Run once against the fresh project.
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Social feed: a copied bot emits a 'copied' event.
CREATE OR REPLACE FUNCTION public.emit_copy_event()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
begin
  if new.copied_from is not null then
    insert into pf_events (type, bot_id, bot_name, market, actor, actor_handle,
                           target_builder, visibility, payload)
    select 'copied', new.id, new.name, new.market, new.owner,
           (select handle from pf_profiles where id = new.owner),
           src.owner, new.visibility,
           jsonb_build_object('from_bot_id', src.id, 'from_bot_name', src.name)
    from pf_bots src where src.id = new.copied_from;
  end if;
  return new;
end; $function$;

DROP TRIGGER IF EXISTS on_bot_copied ON public.pf_bots;
CREATE TRIGGER on_bot_copied AFTER INSERT ON public.pf_bots
  FOR EACH ROW EXECUTE FUNCTION emit_copy_event();

-- Social feed: a new follow emits a 'followed' event.
CREATE OR REPLACE FUNCTION public.emit_follow_event()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
begin
  insert into pf_events (type, actor, actor_handle, target_builder, visibility, payload)
  values ('followed', new.follower,
          (select handle from pf_profiles where id = new.follower),
          new.builder, 'public', '{}'::jsonb);
  return new;
end; $function$;

DROP TRIGGER IF EXISTS on_follow_created ON public.pf_follows;
CREATE TRIGGER on_follow_created AFTER INSERT ON public.pf_follows
  FOR EACH ROW EXECUTE FUNCTION emit_follow_event();
