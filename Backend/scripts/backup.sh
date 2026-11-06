#!/usr/bin/env bash
# PostgreSQL backup for GyanSankalp. Runs from Git Bash, WSL, or any Linux box.
#
#   ./Backend/scripts/backup.sh              # dump into Backend/backups, keep 14
#   KEEP=30 BACKUP_DIR=/mnt/dumps ./Backend/scripts/backup.sh
#
# Covers the database only, and inside it only the public schema: everything the
# application owns lives there, and a dump that also carries a hosted project's
# internal schemas cannot be restored anywhere else. Materials (original PDFs
# and watermarked page JPEGs) live in object storage; copy those with
#   python -m app.scripts.backup_storage --dest-bucket <name>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/db_env.sh"

BACKUP_DIR="${BACKUP_DIR:-$(dirname "$SCRIPT_DIR")/backups}"
KEEP="${KEEP:-14}"

command -v pg_dump >/dev/null || { echo "pg_dump is not on PATH" >&2; exit 1; }
mkdir -p "$BACKUP_DIR"

stamp="$(date -u +%Y%m%d-%H%M%S)"
final="$BACKUP_DIR/gyansankalp-$stamp.dump"
partial="$final.part"
trap 'rm -f "$partial"' EXIT

echo "Dumping $PGDATABASE@$PGHOST:$PGPORT -> $final"
pg_dump --format=custom --no-owner --no-privileges --schema=public --file="$partial" "$pg_url"

# A dump that cannot be listed is not a backup.
pg_restore --list "$partial" >/dev/null
mv "$partial" "$final"
trap - EXIT

size="$(wc -c <"$final")"
echo "Wrote $final ($((size / 1048576)).$(( (size % 1048576) * 10 / 1048576 )) MiB)"

# Retention: newest KEEP dumps survive, anything older goes.
mapfile -t dumps < <(ls -1t "$BACKUP_DIR"/gyansankalp-*.dump 2>/dev/null || true)
total=${#dumps[@]}
if (( total > KEEP )); then
  for old in "${dumps[@]:KEEP}"; do
    echo "Removing expired backup: $old"
    rm -f "$old"
  done
fi
echo "Done. $(( total < KEEP ? total : KEEP )) of $total dump(s) retained, newest: $(basename "${dumps[0]:-$final}")"
