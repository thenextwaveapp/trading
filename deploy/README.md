# Deploy — where the workers run

**Production is the non-US Hetzner VPS, via systemd. Full stop.**

The always-on processes — `engine_worker` (training/trials/sweeps), the paper
fleet, the dashboards, and the market/news scans — run on the VPS as systemd
units (`deploy/systemd/`). The VPS must be non-US because Binance futures returns
451 from US IPs, so the Mac physically cannot run the market scan correctly.

Deploy / update prod:

    bash deploy/systemd/deploy.sh root@HOST        # push code + config, restart units
    bash deploy/systemd/deploy.sh root@HOST pull   # fetch server fleet state

## launchd (`deploy/launchd/`) is DEV-ONLY

It exists for the solo / single-host era and for local development. It is **not**
production and must not behave like it:

- **Never point a local launchd worker at the production Supabase.** A second
  worker polling the same `pf_backtests` / fleet queues races the VPS — whichever
  host grabs a `pending` row runs it, so results depend on which machine (and
  which code version) won. Non-deterministic, and it breaks backtest==live.
- A laptop sleeps, drops wifi, and drifts in dependencies (e.g. TA-Lib present
  locally, absent on the VPS → `unknown indicator: 'RSI'`). The engine's one
  guarantee — one consistent environment — cannot hold across two hosts.
- If you use launchd for local dev, point it at a **dev/branch DB**, not prod.

Stop + unload the local agents (do this on any machine that isn't the sole host):

    for j in engineworker livebot livedash paperfleet fleetdash; do
      launchctl bootout gui/$(id -u)/com.trading.$j 2>/dev/null || true
    done

## For anyone (human or agent) touching this

A worker running on this Mac does **not** mean the Mac is production. Seeing a
live local process is not the architecture — the architecture is: **VPS +
systemd = prod; launchd = dev.** A code fix in `core/` only reaches prod once it
is deployed to the VPS (`deploy/systemd/deploy.sh`) and the units restart;
restarting a local launchd job changes nothing in production.
