-- Least-privilege database role for the GyanSankalp application.
--
-- The app should never connect as a superuser: one SQL bug (or one leaked
-- .env) then means full control of the cluster instead of one database.
-- Migrations still run as the owner because this role has no DDL rights.
--
--   psql -U postgres -d gyansankalp \
--        -v dbname=gyansankalp \
--        -v app_password="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" \
--        -f Backend/scripts/db_roles.sql
--
-- Then point Backend/.env at it:
--   DATABASE_URL=postgresql+psycopg://gyansankalp_app:<that password>@localhost:5433/gyansankalp
--
-- Run every statement below as the database owner (usually "postgres"), and
-- re-run it after adding new tables if you ever create them by hand.

\set ON_ERROR_STOP on

-- Idempotent so re-running after adding a table doesn't abort the whole script.
-- (psql won't substitute variables inside a dollar-quoted block, so the
-- password is set by the ALTER statement below instead.)
DO $do$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gyansankalp_app') THEN
        CREATE ROLE gyansankalp_app LOGIN;
    END IF;
END
$do$;

ALTER ROLE gyansankalp_app LOGIN PASSWORD :'app_password';

-- Stated explicitly so a later "just make it an admin" edit is visible in review.
ALTER ROLE gyansankalp_app NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- One runaway query must not pin a connection forever.
ALTER ROLE gyansankalp_app SET statement_timeout = '5s';
ALTER ROLE gyansankalp_app SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE gyansankalp_app SET lock_timeout = '5s';

GRANT CONNECT, TEMPORARY ON DATABASE :"dbname" TO gyansankalp_app;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO gyansankalp_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gyansankalp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gyansankalp_app;

-- Tables the migration creates after this run are covered too.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gyansankalp_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO gyansankalp_app;

-- alembic_version belongs to the migration role, not the app role.
REVOKE ALL ON TABLE alembic_version FROM gyansankalp_app;
