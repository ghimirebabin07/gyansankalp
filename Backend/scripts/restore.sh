#!/usr/bin/env bash
# Restore a GyanSankalp database dump.
#
#   ./Backend/scripts/restore.sh Backend/backups/gyansankalp-20261031-090000.dump
#   ./Backend/scripts/restore.sh --force <dump>   # replace a non-empty database
#
# The target comes from DATABASE_URL in Backend/.env, so restoring the wrong
# database means pointing at the wrong env file. Check it first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/db_env.sh"

force=0
if [[ "${1:-}" == "--force" ]]; then
  force=1
  shift
fi

dump="${1:-}"
if [[ -z "$dump" || ! -f "$dump" ]]; then
  echo "usage: restore.sh [--force] <dump-file>" >&2
  exit 1
fi

for tool in psql pg_restore; do
  command -v "$tool" >/dev/null || { echo "$tool is not on PATH" >&2; exit 1; }
done

# Readable before destructive: a corrupt dump should never wipe a live database.
pg_restore --list "$dump" >/dev/null

table_count() {
  psql -tAc \
    "select count(*) from information_schema.tables where table_schema = 'public'" \
    "$pg_url"
}

existing="$(table_count)"
if (( existing > 0 )) && (( force == 0 )); then
  echo "$PGDATABASE already holds $existing table(s)." >&2
  echo "Re-run with --force to drop them and restore $dump." >&2
  exit 1
fi

echo "Restoring $dump into $PGDATABASE@$PGHOST:${PGPORT:-5432}"
if (( existing > 0 )); then
  echo "--clean will drop and recreate $existing existing table(s)."
fi
pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$pg_url" "$dump"

echo "Restored. Public tables now: $(table_count)"
