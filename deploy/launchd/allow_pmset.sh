#!/bin/bash
# One-time setup so the dashboard's "keep awake" button works.
#
# The only way a MacBook keeps running with the lid SHUT (no external
# display) is `pmset disablesleep`, which needs root. This installs a
# sudoers rule scoped to exactly those two commands — nothing else gains
# privileges. Run once:
#   sudo bash deploy/launchd/allow_pmset.sh
# Undo:
#   sudo rm /etc/sudoers.d/trading-pmset
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0"; exit 1; }
u=${SUDO_USER:?must be run via sudo, not as root login}
f=/etc/sudoers.d/trading-pmset

cat > "$f" <<EOF
$u ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 1, /usr/bin/pmset -a disablesleep 0
EOF
chmod 440 "$f"
visudo -c -f "$f" >/dev/null || { rm -f "$f"; echo "sudoers validation failed, removed"; exit 1; }
echo "installed $f"
echo "the dashboard's keep-awake toggle now works (http://localhost:8787)"
