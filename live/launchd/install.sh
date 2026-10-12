#!/bin/bash
# Install the live bot + its dashboard as launchd agents. Run once:
#   bash live/launchd/install.sh
# Undo:
#   launchctl bootout gui/$(id -u)/com.trading.livebot
#   launchctl bootout gui/$(id -u)/com.trading.livedash
#   rm ~/Library/LaunchAgents/com.trading.{livebot,livedash}.plist
set -euo pipefail
cd "$(dirname "$0")"

cp com.trading.livebot.plist com.trading.livedash.plist ~/Library/LaunchAgents/
pkill -f 'live/bot\.py' 2>/dev/null && echo "stopped ad-hoc live bot" || true
pkill -f 'live/dashboard\.py' 2>/dev/null && echo "stopped ad-hoc live dash" || true
sleep 2

uid=$(id -u)
launchctl bootout "gui/$uid/com.trading.livebot" 2>/dev/null || true
launchctl bootout "gui/$uid/com.trading.livedash" 2>/dev/null || true
launchctl bootstrap "gui/$uid" ~/Library/LaunchAgents/com.trading.livebot.plist
launchctl bootstrap "gui/$uid" ~/Library/LaunchAgents/com.trading.livedash.plist

sleep 3
echo "---"
launchctl list | grep -E "com.trading.live" || { echo "NOT RUNNING — check live/launchd.err.log"; exit 1; }
echo "---"
echo "live bot (dry until armed) + dashboard installed: http://localhost:8788"
