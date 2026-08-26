#!/usr/bin/env bash
# Regression for GitHub #45: create SERVICE_GROUP and do not hide useradd errors.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL="$REPO_ROOT/install.sh"

fail() { echo "  FAIL  $*" >&2; exit 1; }
pass() { echo "  OK  $*"; }

[[ -f "$INSTALL" ]] || fail "missing $INSTALL"

if grep -nE 'useradd --system --gid "\$SERVICE_GROUP".*2>/dev/null \|\| true' "$INSTALL"; then
  fail "useradd still swallows errors with 2>/dev/null || true"
fi
pass "useradd no longer hides failures"

grep -q 'groupadd --system "\$SERVICE_GROUP"' "$INSTALL" \
  || fail "install.sh does not groupadd --system SERVICE_GROUP"
pass "groupadd --system SERVICE_GROUP is present"

grep -q 'getent group "\$SERVICE_GROUP"' "$INSTALL" \
  || fail "install.sh does not check getent group before groupadd"
pass "getent group is checked before groupadd"

# Simulate the Step 1 control flow with stubs (no real useradd).
step1() {
  SERVICE_GROUP="$1"
  SERVICE_USER="$2"
  existing_groups="$3"
  existing_users="$4"
  groupadd_log="$5"
  useradd_log="$6"
  : >"$groupadd_log"
  : >"$useradd_log"

  getent() {
    [[ "$1" == "group" && " $existing_groups " == *" $2 "* ]]
  }
  id() {
    [[ " $existing_users " == *" $1 "* ]]
  }
  groupadd() {
    echo "$*" >>"$groupadd_log"
  }
  useradd() {
    echo "$*" >>"$useradd_log"
  }

  if getent group "$SERVICE_GROUP" >/dev/null; then
    :
  else
    groupadd --system "$SERVICE_GROUP"
  fi
  if id "$SERVICE_USER" &>/dev/null; then
    :
  else
    useradd --system --gid "$SERVICE_GROUP" --shell /sbin/nologin --home-dir /opt/openvox-gui "$SERVICE_USER"
  fi
}

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

step1 puppet puppet "" "" "$workdir/g1" "$workdir/u1"
[[ "$(cat "$workdir/g1")" == "--system puppet" ]] || fail "missing group created on dedicated console"
[[ "$(cat "$workdir/u1")" == *"--gid puppet"* ]] || fail "useradd not invoked when user missing"
pass "dedicated console: creates puppet group then user"

step1 puppet puppet "puppet" "puppet" "$workdir/g2" "$workdir/u2"
[[ ! -s "$workdir/g2" ]] || fail "groupadd ran on re-install"
[[ ! -s "$workdir/u2" ]] || fail "useradd ran on re-install"
pass "re-run: group and user already exist, no-op"

step1 ovoxgui ovoxgui "" "" "$workdir/g3" "$workdir/u3"
[[ "$(cat "$workdir/g3")" == "--system ovoxgui" ]] || fail "custom group not created"
[[ "$(cat "$workdir/u3")" == *"--gid ovoxgui"* ]] || fail "custom useradd missing --gid"
pass "custom SERVICE_USER/GROUP: creates both"

echo "tests/shell/test_installer_service_user: OK"
