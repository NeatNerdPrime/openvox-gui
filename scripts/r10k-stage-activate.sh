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

# Do NOT source /etc/profile or /root/.bashrc. A sourced `exit` (or set -u
# trip) kills this script with empty Bolt output — inventory tty:true also
# swallows the PTY. Keep PATH explicit.
export HOME=/root
export USER=root
export PATH="/opt/puppetlabs/puppet/bin:/opt/puppetlabs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Git honors root's gitconfig; the Forge client (Puppetfile) does not.
# Load compiler proxy snippets, then fall back to git http.proxy.
for f in /etc/profile.d/*proxy*.sh /etc/profile.d/noproxy.sh; do
  # shellcheck disable=SC1090
  [ -r "$f" ] && . "$f" 2>/dev/null || true
done
if [ -z "${HTTPS_PROXY:-${https_proxy:-}}" ]; then
  _gp=$(git config --global --get https.proxy 2>/dev/null || true)
  [ -z "$_gp" ] && _gp=$(git config --global --get http.proxy 2>/dev/null || true)
  if [ -n "$_gp" ]; then
    export HTTP_PROXY="$_gp" HTTPS_PROXY="$_gp" http_proxy="$_gp" https_proxy="$_gp"
  fi
fi

LOG="${OPENVOX_STAGE_LOG:-/var/tmp/r10k-stage-activate.log}"
_log() {
  # stdout+stderr so Bolt captures it; copy to a file if the PTY eats it.
  printf 'r10k-stage-activate.sh: %s\n' "$*" | tee -a "$LOG" >&2
}

_redact_proxy() {
  printf '%s' "$1" | sed -E 's#(https?://)[^/@:]+:[^/@]+@#\1***:***@#'
}

# Never prompt; a missing GitHub token must fail fast, not hang Stage.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/true

_px="${HTTPS_PROXY:-${https_proxy:-none}}"
_log "start uid=$(id -u) user=$(id -un) host=$(hostname -f 2>/dev/null || hostname) args=$* proxy=$(_redact_proxy "$_px")"

MODE="${1:-}"
shift || true

STAGING="${OPENVOX_STAGING_CODEDIR:-/etc/puppetlabs/code-staging}"
LIVE="${OPENVOX_LIVE_CODEDIR:-/etc/puppetlabs/code}"
R10K_YAML="${OPENVOX_R10K_YAML:-/etc/puppetlabs/r10k/r10k.yaml}"
R10K_BIN="${OPENVOX_R10K_BIN:-}"

# Puppetfile uses https://#{ENV['R10K_TOKEN']}@github.com/…
# /etc/profile.d/*.sh is NOT read by Bolt --run-as root (non-login sudo).
# Source the known env files ourselves. bolt@ does not need this variable.
for f in /etc/puppetlabs/r10k/environment /etc/sysconfig/r10k /etc/profile.d/r10k.sh; do
  if [ -r "$f" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$f"
    set +a
  fi
done
if [ -z "${R10K_TOKEN:-}" ] && [ -f "$R10K_YAML" ]; then
  R10K_TOKEN=$(sed -n 's#.*https://\([^:/@]*\)@github.com.*#\1#p' "$R10K_YAML" | head -1)
  export R10K_TOKEN
fi
if [ -n "${R10K_TOKEN:-}" ]; then
  _log "R10K_TOKEN is set"
else
  _log "R10K_TOKEN is empty — git modules will be https://@github.com/…"
fi

if [ -z "$R10K_BIN" ]; then
  if command -v r10k >/dev/null 2>&1; then
    R10K_BIN=$(command -v r10k)
  elif [ -x /opt/puppetlabs/puppet/bin/r10k ]; then
    R10K_BIN=/opt/puppetlabs/puppet/bin/r10k
  else
    _log "r10k not found"
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
      _log "missing $R10K_YAML"
      exit 1
    fi
    _log "uid=$(id -u) user=$(id -un) r10k=$R10K_BIN yaml=$R10K_YAML"
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
