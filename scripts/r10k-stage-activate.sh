#!/bin/bash
###############################################################################
# r10k multi-host stage / activate helper (clustered code deploy)
#
# stage   — r10k deploy into a staging codedir (default /etc/puppetlabs/code-staging)
# activate — atomically promote staged environments into the live codedir
#
# Usage (via sudo from openvox-gui / bolt):
#   sudo r10k-stage-activate.sh stage [environment] [-pv]
#   sudo r10k-stage-activate.sh activate [environment]
###############################################################################
set -euo pipefail

export HOME=/root
export USER=root
[ -r /etc/profile ] && . /etc/profile 2>/dev/null || true
[ -r /root/.bash_profile ] && . /root/.bash_profile 2>/dev/null || true
[ -r /root/.bashrc ] && . /root/.bashrc 2>/dev/null || true

MODE="${1:-}"
shift || true

STAGING="${OPENVOX_STAGING_CODEDIR:-/etc/puppetlabs/code-staging}"
LIVE="${OPENVOX_LIVE_CODEDIR:-/etc/puppetlabs/code}"
R10K_YAML="${OPENVOX_R10K_YAML:-/etc/puppetlabs/r10k/r10k.yaml}"
R10K_BIN="${OPENVOX_R10K_BIN:-}"

if [ -z "$R10K_BIN" ]; then
  if command -v r10k >/dev/null 2>&1; then
    R10K_BIN=$(command -v r10k)
  elif [ -x /opt/puppetlabs/puppet/bin/r10k ]; then
    R10K_BIN=/opt/puppetlabs/puppet/bin/r10k
  else
    echo "r10k-stage-activate.sh: r10k not found" >&2
    exit 127
  fi
fi

# Arg hardening (same spirit as r10k-deploy.sh)
for arg in "$@"; do
  if [[ "$arg" =~ ^[a-zA-Z0-9_./-]+$ ]] || [[ "$arg" =~ ^--?[a-zA-Z0-9_.=/-]+$ ]]; then
    continue
  fi
  echo "r10k-stage-activate.sh: refusing suspicious arg: $arg" >&2
  exit 64
done

case "$MODE" in
  stage)
    ENV_NAME=""
    EXTRA=()
    if [ $# -ge 1 ] && [[ "$1" != -* ]]; then
      ENV_NAME="$1"
      shift
    fi
    EXTRA=("$@")
    if [ ${#EXTRA[@]} -eq 0 ]; then
      EXTRA=(-pv)
    fi

    mkdir -p "$STAGING/environments"
    # Temporary r10k config: same sources as production, basedir -> staging.
    # Prefer AIO Ruby — compilers always have it. python3+PyYAML often does not.
    # Do not use /tmp for the tempfile if we can help it (CIS /tmp noexec is
    # about execution, but keep config next to staging anyway).
    TMP_CFG=$(mktemp "$STAGING/.r10k-staging.XXXXXX.yaml")
    trap 'rm -f "$TMP_CFG"' EXIT
    if [ ! -f "$R10K_YAML" ]; then
      echo "r10k-stage-activate.sh: missing $R10K_YAML" >&2
      exit 1
    fi
    echo "r10k-stage-activate.sh: uid=$(id -u) user=$(id -un) r10k=$R10K_BIN yaml=$R10K_YAML" >&2
    RUBY_BIN=""
    if [ -x /opt/puppetlabs/puppet/bin/ruby ]; then
      RUBY_BIN=/opt/puppetlabs/puppet/bin/ruby
    elif command -v ruby >/dev/null 2>&1; then
      RUBY_BIN=$(command -v ruby)
    fi
    if [ -n "$RUBY_BIN" ]; then
      "$RUBY_BIN" - "$R10K_YAML" "$TMP_CFG" "$STAGING/environments" <<'RB'
require 'yaml'
src, dst, basedir = ARGV
cfg = YAML.load_file(src)
abort "r10k-stage-activate.sh: empty r10k config" if cfg.nil? || cfg.empty?
sources = cfg['sources'] || cfg[:sources]
abort "r10k-stage-activate.sh: r10k config has no sources" unless sources.is_a?(Hash)
sources.each_value do |srcdef|
  next unless srcdef.is_a?(Hash)
  if srcdef.key?(:basedir)
    srcdef[:basedir] = basedir
  else
    srcdef['basedir'] = basedir
  end
end
File.write(dst, YAML.dump(cfg))
warn "r10k-stage-activate.sh: wrote staging config basedir=#{basedir}"
RB
    else
      python3 - "$R10K_YAML" "$TMP_CFG" "$STAGING/environments" <<'PY'
import sys, yaml
src, dst, basedir = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src) as f:
    cfg = yaml.safe_load(f) or {}
sources = cfg.get("sources") or cfg.get(":sources") or {}
if not sources:
    raise SystemExit("r10k-stage-activate.sh: r10k config has no sources")
for name, srcdef in sources.items():
    if isinstance(srcdef, dict):
        srcdef["basedir"] = basedir
with open(dst, "w") as f:
    yaml.safe_dump(cfg, f, default_flow_style=False)
print(f"r10k-stage-activate.sh: wrote staging config basedir={basedir}", file=sys.stderr)
PY
    fi

    echo "r10k-stage-activate.sh: staging to $STAGING/environments host=$(hostname -f)" >&2
    if [ -n "$ENV_NAME" ]; then
      "$R10K_BIN" deploy environment "$ENV_NAME" "${EXTRA[@]}" --config "$TMP_CFG"
    else
      "$R10K_BIN" deploy environment "${EXTRA[@]}" --config "$TMP_CFG"
    fi
    # Marker for operators / activate race detection
    date -u +%Y-%m-%dT%H:%M:%SZ > "$STAGING/.stage-complete"
    hostname -f >> "$STAGING/.stage-complete"
    echo "r10k-stage-activate.sh: stage complete" >&2
    ;;

  activate)
    ENV_NAME=""
    if [ $# -ge 1 ] && [[ "$1" != -* ]]; then
      ENV_NAME="$1"
    fi
    SRC="$STAGING/environments"
    DST="$LIVE/environments"
    if [ ! -d "$SRC" ]; then
      echo "r10k-stage-activate.sh: staging dir missing: $SRC" >&2
      exit 1
    fi
    mkdir -p "$DST"
    if [ -n "$ENV_NAME" ]; then
      if [ ! -d "$SRC/$ENV_NAME" ]; then
        echo "r10k-stage-activate.sh: staged environment not found: $ENV_NAME" >&2
        exit 1
      fi
      echo "r10k-stage-activate.sh: activating $ENV_NAME -> $DST/$ENV_NAME" >&2
      rsync -a --delete "$SRC/$ENV_NAME/" "$DST/$ENV_NAME/"
    else
      echo "r10k-stage-activate.sh: activating all staged environments -> $DST" >&2
      for envdir in "$SRC"/*; do
        [ -d "$envdir" ] || continue
        ename=$(basename "$envdir")
        rsync -a --delete "$envdir/" "$DST/$ename/"
      done
    fi
    date -u +%Y-%m-%dT%H:%M:%SZ > "$LIVE/.activate-complete"
    hostname -f >> "$LIVE/.activate-complete"
    # Best-effort environment cache flush for puppetserver
    if systemctl is-active --quiet puppetserver 2>/dev/null; then
      curl -sk -X DELETE "https://127.0.0.1:8140/puppet-admin-api/v1/environment-cache" \
        --cert /etc/puppetlabs/puppet/ssl/certs/"$(hostname -f)".pem \
        --key /etc/puppetlabs/puppet/ssl/private_keys/"$(hostname -f)".pem \
        --cacert /etc/puppetlabs/puppet/ssl/certs/ca.pem \
        2>/dev/null || true
    fi
    echo "r10k-stage-activate.sh: activate complete on $(hostname -f)" >&2
    ;;

  *)
    echo "Usage: $0 stage [environment] [-pv] | activate [environment]" >&2
    exit 64
    ;;
esac
