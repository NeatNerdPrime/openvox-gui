#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# ci-pip-audit.sh — Audit backend Python deps (including psycopg2-binary)
#
# Used by .github/workflows/security.yml and runnable locally.
#
# Why a dedicated script:
#   - macOS + bleeding-edge Python often cannot *build* psycopg2-binary
#     from sdist (needs pg_config). CI uses ubuntu-latest + binary wheels.
#   - --only-binary=psycopg2-binary refuses source fallback so the audit
#     always covers the same wheel path production installs use.
#
# Usage:
#   ./scripts/ci-pip-audit.sh              # create .venv-pip-audit, install, audit
#   ./scripts/ci-pip-audit.sh --keep-venv  # leave .venv-pip-audit behind
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQ_FILE="${REPO_ROOT}/backend/requirements.txt"
VENV_DIR="${REPO_ROOT}/.venv-pip-audit"
KEEP_VENV=0

for arg in "$@"; do
  case "$arg" in
    --keep-venv) KEEP_VENV=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$REQ_FILE" ]]; then
  echo "ERROR: missing $REQ_FILE" >&2
  exit 1
fi

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON not found" >&2
  exit 1
fi

echo "==> Python: $($PYTHON --version 2>&1)"
echo "==> Requirements: $REQ_FILE"

cleanup() {
  if [[ "$KEEP_VENV" -eq 0 && -d "$VENV_DIR" ]]; then
    rm -rf "$VENV_DIR"
  fi
}
trap cleanup EXIT

rm -rf "$VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install -q -U pip setuptools wheel pip-audit

echo "==> Installing backend requirements (binary wheel only for psycopg2-binary)"
# Force the manylinux / platform wheel. Fail loud if no wheel exists for
# this interpreter — better than silently auditing a source build or skip.
python -m pip install -q \
  --only-binary=psycopg2-binary \
  -r "$REQ_FILE"

echo "==> Installed psycopg2-binary:"
python -c "import psycopg2; print('  ', psycopg2.__version__, getattr(psycopg2, '__file__', ''))"

echo "==> pip-audit (installed environment, includes transitive deps)"
# Exit non-zero on any known vulnerability (default).
python -m pip_audit --progress-spinner=off --strict

echo "==> pip-audit OK (no known vulnerabilities)"
