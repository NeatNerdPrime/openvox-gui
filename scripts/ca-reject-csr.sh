#!/bin/bash
###############################################################################
# Reject (delete) a pending Puppet/OpenVox certificate signing request.
#
# Used by POST /api/certificates/reject. Validates certname, then:
#   1) Removes CSR PEM under known CA request directories (unsigned only)
#   2) Falls back to `puppetserver ca clean --certname` if no CSR file found
#
# Never follows .. traversal. Never deletes signed certs via rm (clean does).
###############################################################################
set -euo pipefail

CERTNAME="${1:-}"
if [[ -z "$CERTNAME" || ${#CERTNAME} -gt 253 ]]; then
  echo "invalid certname: empty or too long" >&2
  exit 2
fi
if [[ "$CERTNAME" == *..* || "$CERTNAME" == */* || "$CERTNAME" == *\\* ]]; then
  echo "invalid certname: path characters not allowed" >&2
  exit 2
fi
if [[ ! "$CERTNAME" =~ ^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$ ]]; then
  echo "invalid certname: disallowed characters" >&2
  exit 2
fi

DIRS=(
  /etc/puppetlabs/puppet/ssl/ca/requests
  /etc/puppetlabs/puppetserver/ca/requests
  /mnt/openvox-ca/ca/requests
)

removed=0
for d in "${DIRS[@]}"; do
  [[ -d "$d" ]] || continue
  base=$(readlink -f "$d" 2>/dev/null || true)
  [[ -n "$base" && -d "$base" ]] || continue
  f="${d}/${CERTNAME}.pem"
  [[ -e "$f" || -L "$f" ]] || continue
  real=$(readlink -f "$f" 2>/dev/null || true)
  [[ -n "$real" && -f "$real" ]] || continue
  case "$real" in
    "${base}"/*.pem) ;;
    *)
      echo "refusing to delete $real (outside $base)" >&2
      exit 3
      ;;
  esac
  rm -f -- "$real"
  echo "removed pending CSR $real"
  removed=1
done

if [[ "$removed" -eq 1 ]]; then
  exit 0
fi

PS=/opt/puppetlabs/bin/puppetserver
if [[ ! -x "$PS" ]]; then
  echo "no CSR file found and puppetserver CLI missing" >&2
  exit 4
fi

echo "no CSR file on disk; trying puppetserver ca clean --certname ${CERTNAME}"
exec "$PS" ca clean --certname "$CERTNAME"
