#!/bin/bash
###############################################################################
# First-install bootstrap for an OpenVox catalog compiler
#
# Chicken-egg: Puppet will own this later (r10k class + bolt_user). Until
# the control repo is compiling onto this host, run this once as root.
#
# What it does:
#   - git (r10k needs it)
#   - r10k via AIO Ruby gem (/opt/puppetlabs/puppet/bin/r10k)
#   - /etc/puppetlabs/r10k/ (does NOT invent a control-repo URL)
#   - /home/bolt/.bolt/tmp (CIS /tmp is noexec; OpenBolt script run)
#
# Usage (on the compiler):
#   sudo ./scripts/bootstrap-compiler.sh
#   sudo ./scripts/bootstrap-compiler.sh --yaml /path/to/r10k.yaml
#
# Usage (from a console, after bolt@ works):
#   sudo -u bolt bolt script run /opt/openvox-gui/scripts/bootstrap-compiler.sh \
#     --targets ovcompiler2.pdxc-it.corp.int-x.ai,ovcompiler1.atlc-it.corp.int-x.ai \
#     --run-as root --no-tty --project /etc/puppetlabs/bolt
###############################################################################
set -euo pipefail

export PATH="/opt/puppetlabs/puppet/bin:/opt/puppetlabs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# Honor corp proxy if already in the environment. Do not source bashrc
# (a sourced exit would kill this the same way Stage used to die silently).
for f in /etc/profile.d/*proxy*.sh /etc/profile.d/noproxy.sh; do
  # shellcheck disable=SC1090
  [ -r "$f" ] && . "$f" || true
done

YAML_SRC=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yaml)
      YAML_SRC="${2:-}"
      shift 2 || true
      ;;
    --yaml=*)
      YAML_SRC="${1#--yaml=}"
      shift
      ;;
    *)
      echo "bootstrap-compiler.sh: unknown arg: $1" >&2
      exit 64
      ;;
  esac
done

echo "bootstrap-compiler.sh: host=$(hostname -f 2>/dev/null || hostname) uid=$(id -u)"

if [ ! -x /opt/puppetlabs/puppet/bin/gem ]; then
  echo "bootstrap-compiler.sh: AIO gem not found. Install openvox-agent first." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y git
  elif command -v yum >/dev/null 2>&1; then
    yum install -y git
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y git
  else
    echo "bootstrap-compiler.sh: git is required and no package manager found" >&2
    exit 1
  fi
fi
echo "bootstrap-compiler.sh: git=$(command -v git)"

if [ ! -x /opt/puppetlabs/puppet/bin/r10k ]; then
  echo "bootstrap-compiler.sh: installing r10k via AIO gem (proxy=${HTTPS_PROXY:-${https_proxy:-none}})"
  /opt/puppetlabs/puppet/bin/gem install r10k --no-document
else
  echo "bootstrap-compiler.sh: r10k already at /opt/puppetlabs/puppet/bin/r10k"
fi
/opt/puppetlabs/puppet/bin/r10k version

install -d -m 0755 /etc/puppetlabs/r10k
if [ -n "$YAML_SRC" ]; then
  if [ ! -f "$YAML_SRC" ]; then
    echo "bootstrap-compiler.sh: --yaml file not found: $YAML_SRC" >&2
    exit 1
  fi
  cp -a "$YAML_SRC" /etc/puppetlabs/r10k/r10k.yaml
  chmod 0640 /etc/puppetlabs/r10k/r10k.yaml
  echo "bootstrap-compiler.sh: installed $YAML_SRC -> /etc/puppetlabs/r10k/r10k.yaml"
fi

if [ ! -f /etc/puppetlabs/r10k/r10k.yaml ]; then
  echo "bootstrap-compiler.sh: WARNING: /etc/puppetlabs/r10k/r10k.yaml is missing."
  echo "  Copy the working file from ovcompiler1.pdxc (same control-repo URL):"
  echo "    scp ovcompiler1.pdxc-it.corp.int-x.ai:/etc/puppetlabs/r10k/r10k.yaml /etc/puppetlabs/r10k/r10k.yaml"
  echo "  Then re-run or just Stage. Do not invent a remote URL here."
else
  echo "bootstrap-compiler.sh: yaml=/etc/puppetlabs/r10k/r10k.yaml"
fi

if getent passwd bolt >/dev/null 2>&1; then
  install -d -o bolt -g bolt -m 0700 /home/bolt /home/bolt/.bolt /home/bolt/.bolt/tmp
  echo "bootstrap-compiler.sh: /home/bolt/.bolt/tmp ready"
else
  echo "bootstrap-compiler.sh: bolt user not present yet — skip tmpdir (classify bolt_user)"
fi

echo "bootstrap-compiler.sh: done on $(hostname -f 2>/dev/null || hostname)"
