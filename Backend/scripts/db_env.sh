# Shared connection setup for the backup and restore scripts.
# Reads DATABASE_URL from Backend/.env and exports the PG* variables libpq reads.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "No env file at $ENV_FILE" >&2
  exit 1
fi

# DATABASE_URL=postgresql+psycopg://user:pass@host:port/name
db_url="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r')"
if [[ -z "$db_url" ]]; then
  echo "DATABASE_URL missing from $ENV_FILE" >&2
  exit 1
fi

rest="${db_url#*://}"
credentials="${rest%%@*}"
rest="${rest#*@}"
hostport="${rest%%/*}"

export PGUSER="${credentials%%:*}"
export PGDATABASE="${rest#*/}"
if [[ "$credentials" == *:* ]]; then
  export PGPASSWORD="${credentials#*:}"
fi
if [[ "$hostport" == *:* ]]; then
  export PGHOST="${hostport%%:*}"
  export PGPORT="${hostport##*:}"
else
  export PGHOST="$hostport"
fi

pg_url="postgresql://$PGUSER@$PGHOST:${PGPORT:-5432}/$PGDATABASE"
