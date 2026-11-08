-- Feed privacy: a per-builder master "broadcast" switch + server-side gating of
-- the activity feed by each bot's visibility tier.
--
-- What lands in pf_events (public feed) is decided bot-level:
--   Private  -> nothing
--   Results  -> closed trades (exited) only
--   Public   -> live entries, exits, kill-switches, copied
--   followed -> cut for everyone
-- ...and silenced entirely when the owner turns off share_to_feed.
--
-- Applied to project eva-personal-ea (otizdfuhzxwvkbnjiddx) on 2026-11-07.

-- 1) master switch ----------------------------------------------------------
alter table public.pf_profiles
  add column if not exists share_to_feed boolean not null default true;

comment on column public.pf_profiles.share_to_feed is
  'Master switch: broadcast this builder''s non-private bot activity to the global feed.';

-- 2) gating predicate -------------------------------------------------------
-- SECURITY DEFINER so it reads current pf_bots.visibility + pf_profiles.share_to_feed
-- past the viewer's RLS, returning only a boolean (no data leak). Reflects the
-- CURRENT settings, so flipping a bot private / broadcast off hides past events too.
create or replace function public.pf_event_in_feed(_type text, _bot_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select case
    when _type = 'followed' then false
    else exists (
      select 1
      from public.pf_bots b
      join public.pf_profiles p on p.id = b.owner
      where b.id = _bot_id
        and coalesce(p.share_to_feed, true)
        and case _type
              when 'entered'     then b.visibility = 'public'
              when 'kill_switch' then b.visibility = 'public'
              when 'exited'      then b.visibility in ('results', 'public')
              when 'copied'      then b.visibility = 'public'
              else false
            end
    )
  end
$$;

grant execute on function public.pf_event_in_feed(text, uuid) to anon, authenticated;

-- 3) read policy ------------------------------------------------------------
drop policy if exists pf_events_read on public.pf_events;
create policy pf_events_read on public.pf_events
  for select
  using ( public.pf_event_in_feed(type, bot_id) );
