#!/bin/bash
###############################################################################
# cluster-preflight.sh
#
# Operator-facing checks so a clustered console never silently shows a
# short fleet. Exit 0 if all checks pass; 1 if any fail.
#
# Does not change .env. Does not take the GUI off ovdb.corp.
#
#   sudo ./scripts/cluster-preflight.sh
#   sudo ./scripts/cluster-preflight.sh --env /opt/openvox-gui/config/.env
###############################################################################
set -euo pipefail

ENV_FILE="${OPENVOX_GUI_ENV:-/opt/openvox-gui/config/.env}"
while [ $# -gt 0 ]; do
  case "$1" in
    --env) ENV_FILE="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

FAIL=0
ok()   { echo "OK    $*"; }
warn() { echo "WARN  $*"; }
bad()  { echo "FAIL  $*"; FAIL=1; }

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

PDB_HOST="${OPENVOX_GUI_PUPPETDB_HOST:-}"
PDB_PORT="${OPENVOX_GUI_PUPPETDB_PORT:-8081}"
CERT="${OPENVOX_GUI_PUPPET_SSL_CERT:-/etc/puppetlabs/puppet/ssl/certs/$(hostname -f).pem}"
KEY="${OPENVOX_GUI_PUPPET_SSL_KEY:-/etc/puppetlabs/puppet/ssl/private_keys/$(hostname -f).pem}"
CA="${OPENVOX_GUI_PUPPET_SSL_CA:-/etc/puppetlabs/puppet/ssl/certs/ca.pem}"

echo "=== cluster-preflight ($(hostname -f)) ==="

# 1) VIP FQDN must not be pinned in /etc/hosts (files beats DNS).
if [ -n "$PDB_HOST" ] && grep -E "^[^#]*[[:space:]]${PDB_HOST}([[:space:]]|\$)" /etc/hosts >/dev/null 2>&1; then
  bad "/etc/hosts pins ${PDB_HOST} — remove that line so DNS RR works"
  grep -n -E "^[^#]*[[:space:]]${PDB_HOST}" /etc/hosts || true
else
  ok "/etc/hosts does not pin ${PDB_HOST:-PUPPETDB_HOST}"
fi

if [ -n "$PDB_HOST" ]; then
  GETENT=$(getent hosts "$PDB_HOST" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')
  DIG=""
  if command -v dig >/dev/null 2>&1; then
    DIG=$(dig +short "$PDB_HOST" A 2>/dev/null | sort -u | tr '\n' ' ')
  fi
  echo "      getent: ${GETENT:-none}"
  echo "      dig:    ${DIG:-n/a}"
  NGETENT=$(echo "$GETENT" | wc -w | tr -d ' ')
  if [ "${NGETENT:-0}" -lt 2 ] && echo "$PDB_HOST" | grep -Eq '(^|[.])corp([.]|$)'; then
    warn "${PDB_HOST} resolved to ${NGETENT} address(es); a site RR should have ≥2"
  fi
fi

# 2) /nodes count on every A record must match.
if [ -n "$PDB_HOST" ] && [ -f "$CERT" ] && [ -f "$KEY" ] && [ -f "$CA" ]; then
  IPS=$(getent hosts "$PDB_HOST" 2>/dev/null | awk '{print $1}' | sort -u)
  COUNTS=""
  for ip in $IPS; do
    n=$(curl -sk --max-time 15 --cert "$CERT" --key "$KEY" --cacert "$CA" \
      --resolve "${PDB_HOST}:${PDB_PORT}:${ip}" \
      "https://${PDB_HOST}:${PDB_PORT}/pdb/query/v4/nodes" \
      2>/dev/null | python3 -c 'import json,sys
try:
 d=json.load(sys.stdin)
 print(len(d) if isinstance(d,list) else "err")
except Exception:
 print("err")' || echo err)
    echo "      /nodes ${ip} = ${n}"
    COUNTS="${COUNTS} ${n}"
  done
  UNIQ=$(echo "$COUNTS" | tr ' ' '\n' | grep -v '^$' | sort -u | wc -l | tr -d ' ')
  if echo "$COUNTS" | grep -q err; then
    bad "one or more /nodes probes failed (mTLS or timeout)"
  elif [ "${UNIQ:-0}" -gt 1 ]; then
    bad "VIP backends disagree on /nodes count (${COUNTS} ). GUI will flip."
  else
    ok "all resolved VIP addresses agree on /nodes"
  fi
else
  warn "skip /nodes probe (missing host or agent cert/key/ca)"
fi

# 3) Compiler :8140 serial vs disk (local only).
if [ -f /etc/puppetlabs/puppetserver/conf.d/webserver.conf ]; then
  CN=$(hostname -f)
  DISK="/etc/puppetlabs/puppet/ssl/certs/${CN}.pem"
  if [ -f "$DISK" ]; then
    DS=$(openssl x509 -noout -serial -in "$DISK" 2>/dev/null | sed 's/serial=//')
    PS=$(echo | openssl s_client -connect 127.0.0.1:8140 -servername "$CN" 2>/dev/null \
      | openssl x509 -noout -serial 2>/dev/null | sed 's/serial=//')
    if [ -n "$DS" ] && [ "$DS" = "$PS" ]; then
      ok "compiler :8140 serial matches disk ($DS)"
    else
      bad "compiler disk serial=${DS:-none} :8140 serial=${PS:-none} — restart puppetserver or recert"
    fi
  fi
fi

echo "=== result: $([ "$FAIL" -eq 0 ] && echo PASS || echo FAIL) ==="
exit "$FAIL"
