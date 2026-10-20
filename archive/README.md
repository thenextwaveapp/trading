# archive/

Stale / superseded files moved here during the 2026-10-19 cleanup. Nothing
is wired into the running system; safe to delete once you're sure.

| File | What it was | Why archived |
|---|---|---|
| `fleet_dashboard_v2.py` | an abandoned fork of `fleet_dashboard.py` | nothing referenced it; launchd + systemd both run `fleet_dashboard.py` |
| `web-vercel.json` | `web/vercel.json` (Vercel deploy config) | Vercel was dropped 2026-10-19 — the app is served from Hetzner via `fleet_dashboard.py` |
| `Archive.zip` | an old snapshot of `research/` | stale local backup; git is the source of truth |
| `marks.csv.bak` | a backup of `paper/fleet/marks.csv` | superseded by the live file |
