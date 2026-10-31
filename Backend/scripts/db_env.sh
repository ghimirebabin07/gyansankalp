# Shared connection setup for the backup and restore scripts.
#
# An exported DATABASE_URL wins over Backend/.env, so a cron job or an operator
# can point these scripts somewhere else without editing the env file.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "No DATABASE_URL set and no env file at $ENV_FILE" >&2
    exit 1
  fi
  # DATABASE_URL=postgresql+psycopg://user:pass@host:port/name?sslmode=require
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r')"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is missing" >&2
  exit 1
fi

_url="${DATABASE_URL#*://}"
_credentials="${_url%%@*}"
_url="${_url#*@}"
_hostport="${_url%%/*}"
_tail="${_url#*/}"
_database="${_tail%%\?*}"
_query="${_tail#*\?}"
[[ "$_query" == "$_tail" ]] && _query=""

_decode() {
  # Percent-decoding: a password with a space or a % in it is stored encoded.
  local encoded="${1//+/ }"
  printf '%b' "${encoded//%/\\x}"
}

export PGUSER="${_credentials%%:*}"
export PGDATABASE="$_database"
if [[ "$_credentials" == *:* ]]; then
  export PGPASSWORD="$(_decode "${_credentials#*:}")"
fi
if [[ "$_hostport" == *:* ]]; then
  export PGHOST="${_hostport%%:*}"
  export PGPORT="${_hostport##*:}"
else
  export PGHOST="$_hostport"
fi

# libpq reads the usual query-string options from the PG* environment.
for _pair in ${_query//&/ }; do
  case "$_pair" in
    sslmode=*) export PGSSLMODE="${_pair#*=}" ;;
    connect_timeout=*) export PGCONNECT_TIMEOUT="${_pair#*=}" ;;
    *) echo "Ignoring unsupported DATABASE_URL option: $_pair" >&2 ;;
  esac
done

# pg_dump and pg_restore take a conninfo URI; the password stays in PGPASSWORD.
pg_url="postgresql://$PGUSER@${PGHOST:-localhost}:${PGPORT:-5432}/$PGDATABASE"
