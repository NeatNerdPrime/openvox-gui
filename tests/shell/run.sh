#!/usr/bin/env bash
# Shell quality + smoke tests for installer/deploy helpers.
# Invoked by GitHub Actions (job: shell) and scripts/run-ci-local.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

failed=0
pass() { echo "  OK  $*"; }
fail() { echo "  FAIL  $*" >&2; failed=1; }

echo "── bash -n (syntax) ──"
while IFS= read -r f; do
  if bash -n "$f"; then
    pass "bash -n $f"
  else
    fail "bash -n $f"
  fi
done < <(
  find . \
    -path './.git' -prune -o \
    -path './frontend/node_modules' -prune -o \
    -path './backend/venv' -prune -o \
    -path './.venv-pip-audit' -prune -o \
    \( -name '*.sh' -o -name '*.bash' \) -type f -print | sort
)

echo
echo "── help / usage smoke ──"
if ./scripts/bump-version.sh --help >/dev/null; then
  pass "bump-version.sh --help"
else
  fail "bump-version.sh --help"
fi
if ./scripts/ci-pip-audit.sh --help >/dev/null; then
  pass "ci-pip-audit.sh --help"
else
  fail "ci-pip-audit.sh --help"
fi
if ./scripts/ci-quality.sh >/dev/null; then
  pass "ci-quality.sh"
else
  fail "ci-quality.sh"
fi
if bolt-plugin/bin/run-tests --help >/dev/null; then
  pass "bolt-plugin/bin/run-tests --help"
else
  fail "bolt-plugin/bin/run-tests --help"
fi

echo
echo "── installer health probe (#44) ──"
if bash "$REPO_ROOT/tests/shell/test_installer_health_probe.sh"; then
  pass "test_installer_health_probe.sh"
else
  fail "test_installer_health_probe.sh"
fi

echo
echo "── installer service user (#45) ──"
if bash "$REPO_ROOT/tests/shell/test_installer_service_user.sh"; then
  pass "test_installer_service_user.sh"
else
  fail "test_installer_service_user.sh"
fi

echo
echo "── VERSION is present and PEP 440-ish ──"
ver="$(tr -d '[:space:]' < VERSION)"
if [[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.]+)?$ ]]; then
  pass "VERSION=$ver"
else
  fail "VERSION looks invalid: $ver"
fi
if [[ "$ver" == *gamma* ]]; then
  fail "VERSION contains gamma (pip rejects this)"
fi

echo
echo "── heredoc safety (quoted delimiters unless NOTE:) ──"
# Flag unquoted heredocs in .sh files that lack a NOTE comment on the
# preceding line. Project rule: default to << 'EOF'.
heredoc_hits=0
while IFS= read -r line; do
  file="${line%%:*}"
  rest="${line#*:}"
  lineno="${rest%%:*}"
  # Allow files that document the exception immediately above
  prev=$((lineno - 1))
  if [[ "$prev" -ge 1 ]]; then
    prev_text="$(sed -n "${prev}p" "$file")"
    if [[ "$prev_text" == *NOTE:* ]]; then
      continue
    fi
  fi
  echo "  unquoted heredoc without NOTE: $file:$lineno"
  heredoc_hits=$((heredoc_hits + 1))
done < <(
  # Match << EOF / <<EOF / << END but not << 'EOF' / << "EOF" / <<'EOF'
  grep -nR --include='*.sh' --include='*.bash' -E '<<[[:space:]]*[A-Za-z_][A-Za-z0-9_]*' \
    --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=venv \
    . | grep -vE "<<"[[:space:]]*[\'\"] || true
)

# The grep above is advisory for CI logs. install.sh / deploy.sh have
# intentional unquoted heredocs; we do not fail the suite on them.
if [[ "$heredoc_hits" -gt 0 ]]; then
  echo "  note: $heredoc_hits unquoted heredoc(s) without a NOTE comment (advisory)"
else
  pass "no unquoted heredocs missing a NOTE comment"
fi

echo
if [[ "$failed" -eq 0 ]]; then
  echo "tests/shell: all checks passed."
  exit 0
fi
echo "tests/shell: one or more checks failed." >&2
exit 1
