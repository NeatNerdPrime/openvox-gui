#!/bin/bash
###############################################################################
# estate-health-check.sh
#
# Top-to-bottom check of a *clustered* OpenVox GUI console. Assumes VIPs
# (ovdb.corp, ovca.corp, ovcompilers.<site>) — does not tell you to pin
# writers to a single ovdb member.
#
# Run as root on EACH console (openvox.atlc and openvox.pdxc).
#
#   sudo /opt/openvox-gui/scripts/estate-health-check.sh
#
# Exit 0 = all required checks passed. 1 = one or more FAIL.
###############################################################################
set -euo pipefail

ENV_FILE="${OPENVOX_GUI_ENV:-/opt/openvox-gui/config/.env}"
PREFLIGHT="${0%/*}/cluster-preflight.sh"

FAIL=0
ok()   { echo "OK    $*"; }
warn() { echo "WARN  $*"; }
bad()  { echo "FAIL  $*"; FAIL=1; }

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

PDB_HOST="${OPENVOX_GUI_PUPPETDB_HOST:-ovdb.example.com}"
PDB_PORT="${OPENVOX_GUI_PUPPETDB_PORT:-8081}"
CERT="${OPENVOX_GUI_PUPPET_SSL_CERT:-/etc/puppetlabs/puppet/ssl/certs/$(hostname -f).pem}"
KEY="${OPENVOX_GUI_PUPPET_SSL_KEY:-/etc/puppetlabs/puppet/ssl/private_keys/$(hostname -f).pem}"
CA="${OPENVOX_GUI_PUPPET_SSL_CA:-/etc/puppetlabs/puppet/ssl/certs/ca.pem}"
BOLT="${BOLT:-/opt/puppetlabs/bolt/bin/bolt}"
[ -x "$BOLT" ] || BOLT=$(command -v bolt || true)

echo "======== estate-health-check $(hostname -f) ========"

echo
echo "----- 1. Console / VIP (clustered design) -----"
if [ -x "$PREFLIGHT" ]; then
  if bash "$PREFLIGHT" --env "$ENV_FILE"; then
    ok "cluster-preflight passed"
  else
    bad "cluster-preflight failed (VIP /hosts / /nodes mismatch)"
  fi
else
  warn "cluster-preflight.sh not next to this script"
fi

if echo "${PDB_HOST}" | grep -Eq 'ovdb1\.|ovdb2\.'; then
  warn "PUPPETDB_HOST=${PDB_HOST} is a member, not the cluster VIP — GUI will not follow ovdb.corp"
else
  ok "PUPPETDB_HOST=${PDB_HOST} (VIP name, good)"
fi

echo
echo "----- 2. Bolt user + key on this console -----"
if getent passwd bolt >/dev/null; then
  ok "user bolt exists"
else
  bad "user bolt missing — classify this console with profiles::base::bolt_user"
fi
if [ -r /etc/puppetlabs/bolt/id_bolt ]; then
  ok "/etc/puppetlabs/bolt/id_bolt readable"
  sudo -u bolt -H test -r /etc/puppetlabs/bolt/id_bolt \
    && ok "bolt can read id_bolt" \
    || bad "bolt cannot read /etc/puppetlabs/bolt/id_bolt (mode/ownership)"
else
  bad "/etc/puppetlabs/bolt/id_bolt missing — Bolt has no private key"
fi
if [ -x "$BOLT" ]; then
  ok "bolt binary $BOLT"
else
  bad "OpenBolt not installed"
fi

echo
echo "----- 3. Bolt inventory + ENC plugin -----"
INV_ETC="/etc/puppetlabs/bolt/inventory.yaml"
INV_EST="/opt/openvox-gui/data/bolt-inventory.estate.yaml"
for inv in "$INV_ETC" "$INV_EST"; do
  if [ -f "$inv" ]; then
    if grep -q 'host-key-check:[[:space:]]*false' "$inv"; then
      ok "$inv host-key-check: false"
    elif grep -q 'host-key-check:' "$inv"; then
      bad "$inv enables host-key-check — Play will HOST_KEY_ERROR on new hosts"
    else
      warn "$inv has no host-key-check (Bolt default is true)"
    fi
    if grep -q 'openvox_enc' "$inv"; then
      ok "$inv references openvox_enc"
    else
      warn "$inv has no openvox_enc plugin (ENC groups will not resolve)"
    fi
  else
    warn "$inv not present"
  fi
done
if [ -d /etc/puppetlabs/bolt/modules/openvox_enc ]; then
  ok "openvox_enc module installed"
else
  bad "openvox_enc not in /etc/puppetlabs/bolt/modules — ENC inventory plugin missing"
fi
if [ -r /etc/puppetlabs/bolt/.bolt_token ] || sudo -u bolt -H test -r /etc/puppetlabs/bolt/.bolt_token 2>/dev/null; then
  ok ".bolt_token present"
else
  warn "no /etc/puppetlabs/bolt/.bolt_token — ENC plugin may 401 (localhost inventory may still work)"
fi

if [ -x "$BOLT" ] && [ -f "$INV_ETC" ] || [ -f "$INV_EST" ]; then
  INV_USE="$INV_EST"
  [ -f "$INV_USE" ] || INV_USE="$INV_ETC"
  if sudo -u bolt -H "$BOLT" inventory show -i "$INV_USE" --project /etc/puppetlabs/bolt --format json >/tmp/estate-inv.json 2>/tmp/estate-inv.err; then
    N=$(python3 -c 'import json; d=json.load(open("/tmp/estate-inv.json"));
print(len(d.get("targets") or d.get("items") or (d if isinstance(d,list) else [])))' 2>/dev/null || echo 0)
    ok "bolt inventory show → ${N} targets (-i ${INV_USE})"
  else
    bad "bolt inventory show failed"
    tail -15 /tmp/estate-inv.err || true
  fi
fi

echo
echo "----- 4. ENC inventory HTTP (this console) -----"
if curl -sk --max-time 10 "https://127.0.0.1:4567/api/enc/inventory/bolt" -o /tmp/enc-inv.json; then
  if python3 -c 'import json; json.load(open("/tmp/enc-inv.json"))' 2>/dev/null; then
    ok "GET /api/enc/inventory/bolt returned JSON"
  else
    bad "/api/enc/inventory/bolt not JSON (auth or GUI down)"
    head -c 200 /tmp/enc-inv.json; echo
  fi
else
  bad "cannot reach https://127.0.0.1:4567/api/enc/inventory/bolt"
fi

echo
echo "----- 5. Bolt SSH to live /nodes (sample) -----"
if [ -f "$CERT" ] && [ -f "$KEY" ] && [ -f "$CA" ] && [ -x "$BOLT" ]; then
  curl -sk --max-time 20 --cert "$CERT" --key "$KEY" --cacert "$CA" \
    "https://${PDB_HOST}:${PDB_PORT}/pdb/query/v4/nodes" \
    -o /tmp/estate-nodes.json 2>/tmp/estate-nodes.err || true
  python3 - <<'PY' >/tmp/estate-targets.txt
import json
try:
    d=json.load(open("/tmp/estate-nodes.json"))
except Exception:
    d=[]
names=sorted({(x.get("certname") or "") for x in (d if isinstance(d,list) else []) if x.get("certname")})
# skip obvious DNS RR labels
skip=set()
for n in names:
    if n.split(".")[0] in ("ovca", "ovdb") and n.count(".")<=3:
        skip.add(n)
for n in names:
    if n not in skip:
        print(n)
PY
  SAMPLE=$(head -5 /tmp/estate-targets.txt)
  if [ -z "$SAMPLE" ]; then
    warn "no /nodes names to SSH-probe"
  else
    INV_USE="$INV_EST"
    [ -f "$INV_USE" ] || INV_USE="$INV_ETC"
    for t in $SAMPLE; do
      if sudo -u bolt -H "$BOLT" command run 'echo ok' --targets "$t" \
        -i "$INV_USE" --project /etc/puppetlabs/bolt --format json \
        --no-tty >/tmp/estate-ssh.json 2>/tmp/estate-ssh.err; then
        if grep -q HOST_KEY_ERROR /tmp/estate-ssh.json /tmp/estate-ssh.err 2>/dev/null; then
          bad "HOST_KEY_ERROR $t — seed known_hosts or set host-key-check: false"
        elif grep -q '"status":"success"' /tmp/estate-ssh.json 2>/dev/null; then
          ok "bolt echo ok → $t"
        else
          bad "bolt echo failed $t"
          python3 -c 'import json,sys
try:
 d=json.load(open("/tmp/estate-ssh.json"))
 print((d.get("items") or [{}])[0].get("value",{}).get("_error",{}).get("msg","see /tmp/estate-ssh.json")[:200])
except Exception as e:
 print(open("/tmp/estate-ssh.err").read()[:200])
' || tail -5 /tmp/estate-ssh.err
        fi
      else
        bad "bolt command run could not start for $t"
        tail -8 /tmp/estate-ssh.err || true
      fi
    done
  fi
else
  warn "skip SSH sample (missing certs or bolt)"
fi

echo
echo "----- 6. PuppetDB Spock reminder (run on ovdb hosts) -----"
echo "      sudo /opt/openvox-gui/scripts/ensure-puppetdb-spock.sh"
echo "      catalogs+factsets+certnames must be in Spock set default (edges=pdb_nopk)"
echo "      Never sub_resync_table certnames. /nodes follows catalogs."

echo
echo "======== result: $([ "$FAIL" -eq 0 ] && echo PASS || echo FAIL) ========"
exit "$FAIL"
