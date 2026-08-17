#!/bin/bash
###############################################################################
# r10k Deploy Wrapper
#
# This script wraps r10k to ensure it runs with a proper environment,
# regardless of how it's invoked. When called via sudo from the openvox-gui
# systemd service, sudo's env_reset strips environment variables that git
# may need (proxy settings, HOME for gitconfig, etc.). This wrapper
# reconstructs the full root login environment before running r10k.
#
# Usage (called by openvox-gui deploy.py):
#   sudo /opt/openvox-gui/scripts/r10k-deploy.sh [environment] [-pv]
#
# Manual usage:
#   sudo /opt/openvox-gui/scripts/r10k-deploy.sh production -pv
#   sudo /opt/openvox-gui/scripts/r10k-deploy.sh -pv    # all environments
###############################################################################

# ─── Reconstruct root's login environment ─────────────────────
# sudo's env_reset creates a minimal environment. We need the full
# root login environment so git can resolve hosts (via proxy, DNS
# settings, etc.). Source the same files a login shell would.
export HOME=/root
export USER=root

# Source system-wide profile (sets PATH, proxy, etc.)
[ -r /etc/profile ] && . /etc/profile 2>/dev/null || true

# Source root's own shell profile if it exists
[ -r /root/.bash_profile ] && . /root/.bash_profile 2>/dev/null || true
[ -r /root/.bashrc ] && . /root/.bashrc 2>/dev/null || true

# Extract git proxy config and export as env vars (belt and suspenders)
_git_http_proxy=$(git config --global --get http.proxy 2>/dev/null || true)
_git_https_proxy=$(git config --global --get https.proxy 2>/dev/null || true)
[ -n "$_git_http_proxy" ] && export HTTP_PROXY="$_git_http_proxy" http_proxy="$_git_http_proxy"
[ -n "$_git_https_proxy" ] && export HTTPS_PROXY="$_git_https_proxy" https_proxy="$_git_https_proxy"

# Never print proxy userinfo in deploy logs (credentials often live in the URL).
_redact_url() {
    # shellcheck disable=SC2001
    echo "$1" | sed -E 's#(https?://)[^/@:[:space:]]+:[^/@[:space:]]+@#\1***:***@#g'
}

# ─── Diagnostics (visible in deploy output) ───────────────────
echo "r10k-deploy.sh: HOME=$HOME USER=$(whoami) DNS=$(getent hosts github.com 2>/dev/null | head -1 || echo 'FAILED')" >&2
[ -n "$HTTP_PROXY" ] && echo "r10k-deploy.sh: HTTP_PROXY=$(_redact_url "$HTTP_PROXY")" >&2
[ -n "$HTTPS_PROXY" ] && echo "r10k-deploy.sh: HTTPS_PROXY=$(_redact_url "$HTTPS_PROXY")" >&2

# ─── Validate args before passing to r10k (3.3.5-30 hardening) ────────────
#
# r10k-deploy.sh is sudo-enabled with a wildcard arg pattern; that's the
# only way sudoers can express "any optional environment name plus
# optional flags". The wildcard means an attacker who can compose a
# sudo invocation could try to slip in things like `-c /tmp/evil.yaml`
# or weird env names. r10k itself parses these reasonably safely, but
# defense-in-depth: we whitelist what we accept.
#
# Allowed argv elements:
#   * Positional 1 (optional): a Puppet environment name -- letters,
#     digits, underscore, hyphen, dot, slash. Matches what r10k itself
#     allows in environment names.
#   * Any other arg must start with `-` (a flag) and contain only
#     letters, digits, hyphen, underscore, dot, equals (so `-pv` and
#     `--config-file=/path/...` are both OK shape-wise).
for arg in "$@"; do
    if [[ "$arg" =~ ^[a-zA-Z0-9_./-]+$ ]] || \
       [[ "$arg" =~ ^--?[a-zA-Z0-9_.=/-]+$ ]]; then
        continue
    fi
    echo "r10k-deploy.sh: refusing suspicious arg: $arg" >&2
    exit 64
done

# ─── Strict environment allow-list (P0/P1 from systems architect report) ──
# If /opt/openvox-gui/etc/allowed-environments.txt exists, only those
# environment names (one per line) are accepted as the first positional arg.
# This prevents arbitrary branch names from webhook/UI reaching r10k.
# The file can be populated from r10k sources or control-repo branches at install time.
ALLOWED_ENVS_FILE="${OPENVOX_GUI_ALLOWED_ENVS_FILE:-/opt/openvox-gui/etc/allowed-environments.txt}"
if [ -f "$ALLOWED_ENVS_FILE" ]; then
    if [ $# -ge 1 ] && [[ "$1" != -* ]]; then
        if ! grep -qx "$1" "$ALLOWED_ENVS_FILE" 2>/dev/null; then
            echo "r10k-deploy.sh: environment '$1' not in allowed list ($ALLOWED_ENVS_FILE)" >&2
            exit 64
        fi
    fi
fi

# Reject dangerous overrides even if shape passed (extra defense).
for arg in "$@"; do
    if [[ "$arg" == --config-file=* ]] || [[ "$arg" == "-c" ]]; then
        echo "r10k-deploy.sh: refusing --config-file override" >&2
        exit 64
    fi
done

# ─── Locate a working r10k binary ─────────────────────────────
# After Puppet agent / AIO Ruby major bumps (e.g. 3.2 → 4.0), the
# gem binstub at /opt/puppetlabs/puppet/bin/r10k can remain while the
# r10k gem is still only installed under the old RubyGems path, which
# produces: can't find gem r10k (>= 0.a). Prefer an executable that
# actually runs. Also try AIO `ruby -S r10k` and `gem exec`.
_AIO_RUBY="${OPENVOX_AIO_RUBY:-/opt/puppetlabs/puppet/bin/ruby}"
_AIO_GEM="${OPENVOX_AIO_GEM:-/opt/puppetlabs/puppet/bin/gem}"
_R10K_SMOKE_ERR=""

_r10k_smoke_ok() {
    local cmd="$1"
    local err
    err=$(mktemp 2>/dev/null || echo /tmp/r10k-smoke.$$)
    # shellcheck disable=SC2086
    if $cmd version >"$err" 2>&1; then
        rm -f "$err" 2>/dev/null || true
        return 0
    fi
    _R10K_SMOKE_ERR=$(head -c 400 "$err" 2>/dev/null | tr '\n' ' ')
    rm -f "$err" 2>/dev/null || true
    return 1
}

_resolve_r10k() {
    local candidate
    for candidate in \
        /opt/puppetlabs/puppet/bin/r10k \
        /opt/puppetlabs/bin/r10k \
        /usr/local/bin/r10k \
        /usr/bin/r10k \
        "$(command -v r10k 2>/dev/null || true)"
    do
        [ -n "$candidate" ] || continue
        [ -x "$candidate" ] || continue
        if _r10k_smoke_ok "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
        echo "r10k-deploy.sh: candidate failed smoke: $candidate (${_R10K_SMOKE_ERR:-unknown})" >&2
    done

    # AIO Ruby loads gems from the correct RubyGems tree even when the
    # binstub is stale after an agent major bump.
    if [ -x "$_AIO_RUBY" ]; then
        if _r10k_smoke_ok "$_AIO_RUBY -S r10k"; then
            printf '%s\n' "$_AIO_RUBY -S r10k"
            return 0
        fi
        echo "r10k-deploy.sh: AIO ruby -S r10k failed (${_R10K_SMOKE_ERR:-unknown})" >&2
    fi
    if [ -x "$_AIO_GEM" ]; then
        if _r10k_smoke_ok "$_AIO_GEM exec r10k"; then
            printf '%s\n' "$_AIO_GEM exec r10k"
            return 0
        fi
        echo "r10k-deploy.sh: AIO gem exec r10k failed (${_R10K_SMOKE_ERR:-unknown})" >&2
    fi
    return 1
}

R10K_BIN="$(_resolve_r10k || true)"
if [ -z "$R10K_BIN" ]; then
    echo "r10k-deploy.sh: no working r10k found on this host ($(hostname -f 2>/dev/null || hostname))." >&2
    echo "r10k-deploy.sh: On a *clustered* console, use Deploy Now (multi-compiler) or Stage/Activate —" >&2
    echo "r10k-deploy.sh: local r10k is only required on compilers (or single-host AIO)." >&2
    echo "r10k-deploy.sh: reinstall for the current AIO Ruby on this host, e.g.:" >&2
    echo "  sudo /opt/puppetlabs/puppet/bin/gem install r10k --no-document" >&2
    if [ -x "$_AIO_RUBY" ]; then
        echo "r10k-deploy.sh: AIO Ruby: $("$_AIO_RUBY" -v 2>/dev/null || true)" >&2
        "$_AIO_GEM" list r10k 2>/dev/null | head -5 >&2 || true
    fi
    exit 127
fi
# shellcheck disable=SC2086
echo "r10k-deploy.sh: using $R10K_BIN ($($R10K_BIN version 2>/dev/null | head -1))" >&2

# ─── Execute r10k ─────────────────────────────────────────────
# R10K_BIN may be a multi-word form ("ruby -S r10k" / "gem exec r10k").
# shellcheck disable=SC2086
exec $R10K_BIN deploy environment "$@"
