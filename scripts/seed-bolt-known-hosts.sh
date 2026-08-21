#!/bin/bash
###############################################################################
# seed-bolt-known-hosts.sh
#
# ssh-keyscan every live /nodes certname (and cluster members) into
# bolt's known_hosts on THIS console. Does not disable host-key-check
# globally. Run on each console after new hosts appear.
#
#   sudo /opt/openvox-gui/scripts/seed-bolt-known-hosts.sh
###############################################################################
set -euo pipefail

ENV_FILE="${OPENVOX_GUI_ENV:-/opt/openvox-gui/config/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

PDB_HOST="${OPENVOX_GUI_PUPPETDB_HOST:-ovdb.corp.int-x.ai}"
PDB_PORT="${OPENVOX_GUI_PUPPETDB_PORT:-8081}"
CERT="${OPENVOX_GUI_PUPPET_SSL_CERT:-/etc/puppetlabs/puppet/ssl/certs/$(hostname -f).pem}"
KEY="${OPENVOX_GUI_PUPPET_SSL_KEY:-/etc/puppetlabs/puppet/ssl/private_keys/$(hostname -f).pem}"
CA="${OPENVOX_GUI_PUPPET_SSL_CA:-/etc/puppetlabs/puppet/ssl/certs/ca.pem}"
KH="/home/bolt/.ssh/known_hosts"

if ! getent passwd bolt >/dev/null; then
  echo "user bolt missing" >&2
  exit 1
fi
install -d -o bolt -g bolt -m 700 /home/bolt/.ssh
touch "$KH"
chown bolt:bolt "$KH"
chmod 644 "$KH"

TMP=$(mktemp)
if [ -f "$CERT" ] && [ -f "$KEY" ] && [ -f "$CA" ]; then
  curl -sk --max-time 20 --cert "$CERT" --key "$KEY" --cacert "$CA" \
    "https://${PDB_HOST}:${PDB_PORT}/pdb/query/v4/nodes" \
    | python3 -c 'import json,sys
d=json.load(sys.stdin)
for x in (d if isinstance(d,list) else []):
    n=x.get("certname") or ""
    if n: print(n)
' >>"$TMP" || true
fi
# Always include cluster members from config if present
if [ -f /opt/openvox-gui/data/cluster_config.json ]; then
  python3 - <<'PY' >>"$TMP"
import json
p="/opt/openvox-gui/data/cluster_config.json"
try:
    d=json.load(open(p))
except Exception:
    raise SystemExit
for k in ("compilers","puppetdb_nodes","ca_nodes","code_deploy_targets"):
    for h in d.get(k) or []:
        print(h)
PY
fi
sort -u "$TMP" -o "$TMP"
echo "keyscan $(wc -l < "$TMP") names → $KH"
while read -r h; do
  [ -n "$h" ] || continue
  sudo -u bolt -H ssh-keyscan -T 5 -t rsa,ecdsa,ed25519 "$h" >>"$KH" 2>/dev/null || \
    echo "WARN  ssh-keyscan failed $h"
done <"$TMP"
chown bolt:bolt "$KH"
# drop duplicate lines
sort -u "$KH" -o "$KH"
chown bolt:bolt "$KH"
rm -f "$TMP"
echo "done $KH ($(wc -l < "$KH") lines)"
