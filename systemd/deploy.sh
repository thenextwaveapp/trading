#!/bin/bash
# Deploy the paper fleet to a Linux VPS (systemd replaces launchd).
# The VPS must be non-US — Binance futures API returns 451 from US IPs.
#
#   bash systemd/deploy.sh root@HOST        # first deploy, and every code/config update
#   bash systemd/deploy.sh root@HOST pull   # fetch server fleet state -> paper/fleet_vps/
#
# State rules: the first deploy seeds paper/fleet/ from this machine (books
# keep their equity); after that the server's copy is the evidence record and
# is never overwritten — code and fleet_config.json are pushed, state is not.
set -euo pipefail
HOST=${1:?usage: deploy.sh user@host [pull]}
DEST=/opt/trading
cd "$(dirname "$0")/.."

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

# engine runtime + weld modules (spec_runtime/fleet_source) + the core strategy
# library. core/ needs numpy+TA-Lib from the engine-venv the service runs under.
rsync -az paper_fleet.py paper_trader.py regime.py weather.py \
          spec_runtime.py fleet_source.py fleet_dashboard.py \
          fleet_config.json "$HOST:$DEST/"
rsync -az --exclude=__pycache__ core "$HOST:$DEST/"
rsync -az paper/universe60.json "$HOST:$DEST/paper/"
rsync -az assets "$HOST:$DEST/"

# build + push the React dashboard; fleet_dashboard.py serves it from web_dist/
( cd web && npm run build )
rsync -az --delete web/dist/ "$HOST:$DEST/web_dist/"
rsync -az --ignore-existing paper/fleet/ "$HOST:$DEST/paper/fleet/"
rsync -az systemd/trading-paperfleet.service \
          systemd/trading-fleetdash.service "$HOST:/etc/systemd/system/"

ssh "$HOST" "chown -R trading: $DEST
             systemctl daemon-reload
             systemctl enable --now trading-paperfleet trading-fleetdash
             systemctl restart trading-paperfleet trading-fleetdash
             sleep 3
             systemctl is-active trading-paperfleet trading-fleetdash"

echo "---"
echo "dashboard:  https://fleet.presencenet.io   (React UI + API, served by fleet_dashboard.py)"
echo "local:      ssh -L 8787:localhost:8787 $HOST   then http://localhost:8787"
echo "logs:       ssh $HOST journalctl -u trading-paperfleet -f"
echo
echo "then stop the Mac agents so only one fleet collects evidence:"
echo "  launchctl bootout gui/\$(id -u)/com.trading.paperfleet"
echo "  launchctl bootout gui/\$(id -u)/com.trading.fleetdash"
