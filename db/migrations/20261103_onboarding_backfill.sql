-- The first-run onboarding funnel gates on pf_profiles.onboarded_at being null.
-- Existing accounts predate the funnel, so stamp them as already onboarded —
-- onboarding is for new signups only, not a retro-active interruption.
--
-- Safe to run once; new rows keep onboarded_at = null (set by the funnel on
-- completion) and are unaffected.

update public.pf_profiles
set onboarded_at = coalesce(created_at, now())
where onboarded_at is null;
