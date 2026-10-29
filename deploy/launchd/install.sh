#!/bin/bash
# DEV-ONLY — NOT production. Production runs on the non-US Hetzner VPS via
# systemd (see deploy/README.md and deploy/systemd/). Do NOT run these agents
# against the production Supabase: a local worker races the VPS for the same job
# queue. Use launchd only as the sole host (single-user) or for local dev against
# a dev/branch DB.
#
# Install the paper fleet + dashboard as launchd agents (survive terminal
# closes, auto-restart on crash, auto-start on login). Run once:
#   bash deploy/launchd/install.sh
# Undo:
#   launchctl bootout gui/$(id -u)/com.trading.paperfleet
#   launchctl bootout gui/$(id -u)/com.trading.fleetdash
#   rm ~/Library/LaunchAgents/com.trading.{paperfleet,fleetdash}.plist
set -euo pipefail
cd "$(dirname "$0")"

cp com.trading.paperfleet.plist com.trading.fleetdash.plist com.trading.engineworker.plist ~/Library/LaunchAgents/

# stop any ad-hoc fleet/dashboard first (state lives in JSON; restart is safe,
# open positions replay their exits from candle history)
pkill -f 'paper_fleet\.py$' 2>/dev/null && echo "stopped ad-hoc fleet" || true
pkill -f 'fleet_dashboard\.py' 2>/dev/null && echo "stopped ad-hoc dashboard" || true
pkill -f 'runtime\.engine_worker' 2>/dev/null && echo "stopped ad-hoc engine worker" || true
sleep 2

uid=$(id -u)
launchctl bootout "gui/$uid/com.trading.paperfleet" 2>/dev/null || true
launchctl bootout "gui/$uid/com.trading.fleetdash" 2>/dev/null || true
launchctl bootout "gui/$uid/com.trading.engineworker" 2>/dev/null || true
launchctl bootstrap "gui/$uid" ~/Library/LaunchAgents/com.trading.paperfleet.plist
launchctl bootstrap "gui/$uid" ~/Library/LaunchAgents/com.trading.fleetdash.plist
launchctl bootstrap "gui/$uid" ~/Library/LaunchAgents/com.trading.engineworker.plist

sleep 3
echo "---"
launchctl list | grep com.trading || { echo "AGENTS NOT RUNNING — check paper/fleet/launchd.err.log"; exit 1; }
echo "---"
echo "fleet + dashboard installed. Dashboard: http://localhost:8787"
