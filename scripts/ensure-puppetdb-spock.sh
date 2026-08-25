#!/bin/bash
###############################################################################
# ensure-puppetdb-spock.sh
#
# Idempotent grants + warnings for OpenVoxDB (database puppetdb) so Spock
# table-sync / apply does not crash-loop on PG17 origin functions.
#
#   sudo ./scripts/ensure-puppetdb-spock.sh
#   sudo ./scripts/ensure-puppetdb-spock.sh --role repl_user --db puppetdb
###############################################################################
set -euo pipefail

ROLE="${SPOCK_REPL_USER:-repl_user}"
DB="${PUPPETDB_DB:-puppetdb}"
while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE="${2:-}"; shift 2 ;;
    --db) DB="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

psql_db() { sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=0 "$@"; }

echo "ensure-puppetdb-spock: db=${DB} role=${ROLE} host=$(hostname -f)"

psql_db <<SQL
GRANT EXECUTE ON FUNCTION pg_catalog.pg_replication_origin_oid(text) TO ${ROLE};
GRANT EXECUTE ON FUNCTION pg_catalog.pg_replication_origin_session_setup(text) TO ${ROLE};
GRANT EXECUTE ON FUNCTION pg_catalog.pg_replication_origin_session_reset() TO ${ROLE};
GRANT EXECUTE ON FUNCTION pg_catalog.pg_replication_origin_advance(text, pg_lsn) TO ${ROLE};
GRANT EXECUTE ON FUNCTION pg_catalog.pg_replication_origin_create(text) TO ${ROLE};
GRANT EXECUTE ON FUNCTION pg_catalog.pg_replication_origin_drop(text) TO ${ROLE};
SQL

echo "OK granted pg_replication_origin_* to ${ROLE}"

psql_db -c \
  "SELECT relname, set_name FROM spock.tables WHERE relname IN ('certnames','factsets','catalogs','catalog_resources','edges','reports') ORDER BY 1;" \
  2>/dev/null || echo "WARN: no spock.tables (extension missing on this DB?)"

psql_db -c \
  "SELECT sync_relname, sync_status FROM spock.local_sync_status WHERE sync_relname IS NOT NULL;" \
  2>/dev/null || true

echo "NOTE: do not run sub_resync_table on certnames or catalogs (FK parents)."
echo "NOTE: /nodes follows catalogs, not SQL INSERT into certnames/factsets."
