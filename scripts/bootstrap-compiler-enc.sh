#!/bin/bash
###############################################################################
# First-install ENC wiring for an OpenVox catalog compiler
#
# Compilers (not consoles) run external_nodes at catalog compile time.
# This script:
#   - installs enc.py (default /usr/local/bin/enc.py — estate standard)
#   - writes /etc/sysconfig/openvox-enc with OPENVOX_GUI_API_BASE
#   - adds a puppetserver systemd drop-in so the unit loads that env
#     (interactive shells are NOT enough — puppetserver must load the file)
#   - sets node_terminus=exec + external_nodes in puppet.conf [server]
#
# Consoles only need a copy of this script under /opt/openvox-gui/scripts
# so operators can Bolt-run it onto compilers. The GUI process itself
# does not call enc.py.
#
# Multi-console / split SQLite:
#   OPENVOX_GUI_API_BASE is tried in order; first HTTP 200 wins.
#   Put the console that holds classification FIRST until both GUIs share
#   Postgres. Example: ATLC has data, PDXC is empty → list ATLC first.
#
# Usage (on a compiler as root):
#   sudo ./scripts/bootstrap-compiler-enc.sh \
#     --api-base 'https://openvox.atlc.example.com:4567,https://openvox.pdxc.example.com:4567'
#
# From a console (after bolt@ works):
#   sudo -u bolt bolt script run /opt/openvox-gui/scripts/bootstrap-compiler-enc.sh \
#     --targets ovcompiler1.example.com,ovcompiler2.example.com \
#     --run-as root --no-tty --project /etc/puppetlabs/bolt -- \
#     --api-base 'https://openvox.atlc.example.com:4567,https://openvox.pdxc.example.com:4567' \
#     --enc-src /opt/openvox-gui/scripts/enc.py \
#     --force --restart
#
# Co-located single-server (GUI on the same host as puppetserver):
#   install.sh calls this with --api-base https://localhost:${APP_PORT}
#   and --enc-src ${INSTALL_DIR}/scripts/enc.py (dest still /usr/local/bin/enc.py)
###############################################################################
set -euo pipefail

export PATH="/opt/puppetlabs/puppet/bin:/opt/puppetlabs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

API_BASE=""
ENC_SRC=""
# Runtime path for external_nodes on compilers (not the console package tree).
ENC_DEST="/usr/local/bin/enc.py"
SYSCONFIG="/etc/sysconfig/openvox-enc"
PUPPET_CONF="/etc/puppetlabs/puppet/puppet.conf"
DROPIN_DIR="/etc/systemd/system/puppetserver.service.d"
DROPIN_FILE="${DROPIN_DIR}/openvox-enc.conf"
DO_PUPPET_CONF="true"
DO_RESTART="false"
# When true, only write env/drop-in if missing (never clobber site values)
PRESERVE_EXISTING="true"

usage() {
  sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'
  exit 64
}

while [ $# -gt 0 ]; do
  case "$1" in
    --api-base)
      API_BASE="${2:-}"
      shift 2 || true
      ;;
    --api-base=*)
      API_BASE="${1#--api-base=}"
      shift
      ;;
    --enc-src)
      ENC_SRC="${2:-}"
      shift 2 || true
      ;;
    --enc-src=*)
      ENC_SRC="${1#--enc-src=}"
      shift
      ;;
    --enc-dest)
      ENC_DEST="${2:-}"
      shift 2 || true
      ;;
    --enc-dest=*)
      ENC_DEST="${1#--enc-dest=}"
      shift
      ;;
    --sysconfig)
      SYSCONFIG="${2:-}"
      shift 2 || true
      ;;
    --sysconfig=*)
      SYSCONFIG="${1#--sysconfig=}"
      shift
      ;;
    --puppet-conf)
      PUPPET_CONF="${2:-}"
      shift 2 || true
      ;;
    --no-puppet-conf)
      DO_PUPPET_CONF="false"
      shift
      ;;
    --restart)
      DO_RESTART="true"
      shift
      ;;
    --force)
      PRESERVE_EXISTING="false"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "bootstrap-compiler-enc.sh: unknown arg: $1" >&2
      usage
      ;;
  esac
done

echo "bootstrap-compiler-enc.sh: host=$(hostname -f 2>/dev/null || hostname) uid=$(id -u)"

if [ "$(id -u)" -ne 0 ]; then
  echo "bootstrap-compiler-enc.sh: must run as root" >&2
  exit 1
fi

# Resolve enc.py source: explicit flag → sibling of this script → install tree
if [ -z "$ENC_SRC" ]; then
  HERE="$(cd "$(dirname "$0")" && pwd)"
  for cand in \
    "${HERE}/enc.py" \
    /opt/openvox-gui/scripts/enc.py \
    /usr/local/share/openvox-gui/enc.py
  do
    if [ -f "$cand" ]; then
      ENC_SRC="$cand"
      break
    fi
  done
fi

if [ -z "$ENC_SRC" ] || [ ! -f "$ENC_SRC" ]; then
  echo "bootstrap-compiler-enc.sh: enc.py not found. Pass --enc-src /path/to/enc.py" >&2
  exit 1
fi

install -d -m 0755 "$(dirname "$ENC_DEST")"
if [ "$(readlink -f "$ENC_SRC" 2>/dev/null || echo "$ENC_SRC")" = \
   "$(readlink -f "$ENC_DEST" 2>/dev/null || echo "$ENC_DEST")" ]; then
  chmod 0755 "$ENC_DEST"
  echo "bootstrap-compiler-enc.sh: enc.py already at $ENC_DEST (chmod 0755)"
else
  install -m 0755 "$ENC_SRC" "$ENC_DEST"
  echo "bootstrap-compiler-enc.sh: installed $ENC_SRC -> $ENC_DEST"
fi

# API base: flag, existing sysconfig, or localhost default for co-located
if [ -z "$API_BASE" ] && [ -f "$SYSCONFIG" ]; then
  # shellcheck disable=SC1090
  API_BASE="$(grep -E '^OPENVOX_GUI_API_BASE=' "$SYSCONFIG" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi
if [ -z "$API_BASE" ]; then
  API_BASE="https://localhost:4567"
  echo "bootstrap-compiler-enc.sh: WARNING: no --api-base; defaulting to $API_BASE"
  echo "  Clustered estates MUST pass both console URLs (comma-separated)."
fi

if [ -f "$SYSCONFIG" ] && [ "$PRESERVE_EXISTING" = "true" ]; then
  EXISTING="$(grep -E '^OPENVOX_GUI_API_BASE=' "$SYSCONFIG" 2>/dev/null | tail -1 || true)"
  if [ -n "$EXISTING" ]; then
    echo "bootstrap-compiler-enc.sh: keeping existing $SYSCONFIG ($EXISTING)"
  else
    umask 022
    printf 'OPENVOX_GUI_API_BASE=%s\n' "$API_BASE" > "$SYSCONFIG"
    chmod 0644 "$SYSCONFIG"
    echo "bootstrap-compiler-enc.sh: wrote $SYSCONFIG"
  fi
else
  umask 022
  printf 'OPENVOX_GUI_API_BASE=%s\n' "$API_BASE" > "$SYSCONFIG"
  chmod 0644 "$SYSCONFIG"
  echo "bootstrap-compiler-enc.sh: wrote $SYSCONFIG (OPENVOX_GUI_API_BASE=$API_BASE)"
fi

install -d -m 0755 "$DROPIN_DIR"
if [ -f "$DROPIN_FILE" ] && [ "$PRESERVE_EXISTING" = "true" ]; then
  echo "bootstrap-compiler-enc.sh: keeping existing $DROPIN_FILE"
else
  cat > "$DROPIN_FILE" << EOF
# Managed by openvox-gui scripts/bootstrap-compiler-enc.sh
# Loads OPENVOX_GUI_API_BASE for enc.py (external_nodes).
[Service]
EnvironmentFile=-${SYSCONFIG}
EOF
  chmod 0644 "$DROPIN_FILE"
  echo "bootstrap-compiler-enc.sh: wrote $DROPIN_FILE"
fi

if [ "$DO_PUPPET_CONF" = "true" ]; then
  if [ ! -f "$PUPPET_CONF" ]; then
    echo "bootstrap-compiler-enc.sh: WARNING: $PUPPET_CONF missing — skip puppet.conf" >&2
  else
    # Ensure [server] section exists
    if ! grep -qE '^\[server\]' "$PUPPET_CONF"; then
      printf '\n[server]\n' >> "$PUPPET_CONF"
      echo "bootstrap-compiler-enc.sh: added [server] section to $PUPPET_CONF"
    fi
    # node_terminus
    if grep -qE '^[[:space:]]*node_terminus[[:space:]]*=' "$PUPPET_CONF"; then
      sed -i 's|^[[:space:]]*node_terminus[[:space:]]*=.*|    node_terminus = exec|' "$PUPPET_CONF"
    else
      # Insert after [server]
      sed -i '/^\[server\]/a\    node_terminus = exec' "$PUPPET_CONF"
    fi
    # external_nodes
    if grep -qE '^[[:space:]]*external_nodes[[:space:]]*=' "$PUPPET_CONF"; then
      sed -i "s|^[[:space:]]*external_nodes[[:space:]]*=.*|    external_nodes = ${ENC_DEST}|" "$PUPPET_CONF"
    else
      sed -i "/^[[:space:]]*node_terminus[[:space:]]*=/a\\    external_nodes = ${ENC_DEST}" "$PUPPET_CONF"
    fi
    echo "bootstrap-compiler-enc.sh: puppet.conf node_terminus=exec external_nodes=${ENC_DEST}"
  fi
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
  if [ "$DO_RESTART" = "true" ]; then
    if systemctl is-active --quiet puppetserver 2>/dev/null; then
      systemctl restart puppetserver
      echo "bootstrap-compiler-enc.sh: restarted puppetserver"
    else
      echo "bootstrap-compiler-enc.sh: puppetserver not active — skip restart"
    fi
  else
    echo "bootstrap-compiler-enc.sh: run 'systemctl daemon-reload && systemctl restart puppetserver' when ready"
  fi
fi

# Smoke check without needing a live agent path
if [ -x "$ENC_DEST" ]; then
  # shellcheck disable=SC1090
  set -a
  # shellcheck disable=SC1090
  [ -f "$SYSCONFIG" ] && . "$SYSCONFIG" || true
  set +a
  SMOKE_OUT="$("$ENC_DEST" "bootstrap-enc-smoke.local" 2>/dev/null || true)"
  if echo "$SMOKE_OUT" | grep -qE 'environment:|classes:'; then
    echo "bootstrap-compiler-enc.sh: smoke OK (enc.py returned YAML)"
  else
    echo "bootstrap-compiler-enc.sh: smoke note — enc.py did not return YAML yet"
    echo "  (console may be down or API base wrong; fix OPENVOX_GUI_API_BASE and re-run)"
  fi
fi

echo "bootstrap-compiler-enc.sh: done on $(hostname -f 2>/dev/null || hostname)"
