#!/bin/bash
# Deploy the paper fleet to a Linux VPS (systemd replaces launchd).
# The VPS must be non-US — Binance futures API returns 451 from US IPs.
#
#   bash deploy/systemd/deploy.sh root@HOST        # first deploy, and every code/config update
#   bash deploy/systemd/deploy.sh root@HOST pull   # fetch server fleet state -> paper/fleet_vps/
#
# State rules: the first deploy seeds paper/fleet/ from this machine (books
# keep their equity); after that the server's copy is the evidence record and
# is never overwritten — code is pushed, state is not.
set -euo pipefail
HOST=${1:?usage: deploy.sh user@host [pull]}
DEST=/opt/trading
cd "$(dirname "$0")/../.."

if [ "${2:-}" = pull ]; then
    mkdir -p paper/fleet_vps
    rsync -az "$HOST:$DEST/paper/fleet/" paper/fleet_vps/
    echo "server fleet state -> paper/fleet_vps/"
    exit 0
fi

ssh "$HOST" "id trading >/dev/null 2>&1 || useradd -r -m -d $DEST -s /usr/sbin/nologin trading
             mkdir -p $DEST/paper/fleet
             printf 'trading ALL=(root) NOPASSWD: /usr/bin/systemctl stop trading-paperfleet, /usr/bin/systemctl start trading-paperfleet, /usr/bin/systemctl restart trading-paperfleet\n' > /etc/sudoers.d/trading-fleet
             chmod 440 /etc/sudoers.d/trading-fleet"

# services live in runtime/ (run via `python -m runtime.<service>`); the core
# strategy library in core/ needs numpy+TA-Lib from the engine-venv the service
# runs under. Data/config (paper/, assets/, web_dist/) stay at the box root —
# runtime modules resolve them relative to the repo root.
rsync -az --exclude=__pycache__ runtime core "$HOST:$DEST/"
# rsync has no --delete, so remove modules that moved/were retired (box keeps
# stale copies otherwise): old flat box-root files, and the runtime/ files that
# moved into the fleet/, server/, scan/ packages (or were deleted).
ssh "$HOST" "cd $DEST && rm -f paper_fleet.py paper_trader.py spec_runtime.py fleet_source.py fleet_dashboard.py regime.py weather.py && rm -f runtime/paper_fleet.py runtime/paper_trader.py runtime/fleet_dashboard.py runtime/market_scan.py runtime/news_scan.py runtime/fleet_source.py runtime/fleet_ops.py"
rsync -az assets "$HOST:$DEST/"

# build + push the React app; runtime.server.app serves it from web_dist/
( cd web && npm run build )
rsync -az --delete web/dist/ "$HOST:$DEST/web_dist/"
rsync -az --ignore-existing paper/fleet/ "$HOST:$DEST/paper/fleet/"
rsync -az deploy/systemd/trading-paperfleet.service \
          deploy/systemd/trading-fleetdash.service \
          deploy/systemd/trading-engine-worker.service \
          deploy/systemd/trading-market-scan.service \
          deploy/systemd/trading-news-scan.service "$HOST:/etc/systemd/system/"

ssh "$HOST" "chown -R trading: $DEST
             systemctl daemon-reload
             systemctl enable --now trading-paperfleet trading-fleetdash trading-engine-worker trading-market-scan trading-news-scan
             systemctl restart trading-paperfleet trading-fleetdash trading-engine-worker trading-market-scan trading-news-scan
             sleep 3
             systemctl is-active trading-paperfleet trading-fleetdash trading-engine-worker trading-market-scan trading-news-scan"

echo "---"
echo "dashboard:  https://fleet.presencenet.io   (React UI + API, served by runtime.server.app)"
echo "local:      ssh -L 8787:localhost:8787 $HOST   then http://localhost:8787"
echo "logs:       ssh $HOST journalctl -u trading-paperfleet -f"
echo
echo "then stop the Mac agents so only one fleet collects evidence:"
echo "  launchctl bootout gui/\$(id -u)/com.trading.paperfleet"
echo "  launchctl bootout gui/\$(id -u)/com.trading.fleetdash"
