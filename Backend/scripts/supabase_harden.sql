-- Close the Supabase "publishable key" hole in the GyanSankalp database.
--
-- Supabase grants every table it creates in `public` to the roles `anon` and
-- `authenticated`, and turns Row Level Security off for tables that are not
-- created through its own tooling. `anon` is Supabase's PUBLISHABLE key: it is
-- shipped inside browser apps on purpose and is not a secret.
--
-- The consequence here is that, before this script runs, any holder of that
-- publishable key can call PostgREST (https://<project-ref>.supabase.co/rest/v1)
-- and read, rewrite or DELETE every row in every table - students' names,
-- emails, phone numbers and Argon2 password hashes, staff accounts, live OTP
-- hashes, refresh tokens - because the only thing separating a client from a
-- table is the grant plus RLS, and both were at their permissive default.
--
-- This application never uses PostgREST. Every query goes through the FastAPI
-- backend, which connects as `postgres` and enforces authorization in SQL. So
-- the correct configuration is to hand `anon` and `authenticated` nothing.
--
--   Run it in the Supabase dashboard: SQL Editor -> New query -> Run.
--   It is idempotent, so re-run it after any migration that adds tables.
--
-- Nothing here touches `service_role` (a secret key, and the role Supabase's
-- own internals use) or the `auth`/`storage`/`realtime` schemas, so sign-up
-- mail, Storage and dashboards keep working.

-- Leave the line below commented when running through the Supabase SQL Editor:
-- a backslash command is a psql feature, and the dashboard's parser rejects it
-- rather than ignoring it. Uncomment it when running this file with psql, so a
-- failure partway through stops the script instead of leaving half the grants
-- revoked.
-- \set ON_ERROR_STOP on

-- 1. Take every table and sequence in public away from the two client roles.
--    Skipped silently when the roles do not exist, which is the case on a
--    local Postgres, so this file is safe to rehearse anywhere.
DO $do$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', 'anon');
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', 'anon');
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM %I', 'anon');
    END IF;

    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', 'authenticated');
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', 'authenticated');
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM %I', 'authenticated');
    END IF;
END
$do$;

-- 2. Stop future tables from being handed back. Supabase installs default
--    privileges for `postgres` that grant everything to both roles, so without
--    this step the next migration silently re-opens the hole. Only the current
--    role's own defaults can be altered, and alembic creates tables as
--    `postgres`, which is exactly the one that needs fixing.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

-- 3. Row Level Security as the second barrier. A table with RLS enabled and no
--    policies returns nothing to a non-owner role, so even a re-grant by later
--    Supabase tooling would not leak rows. Table owners bypass RLS unless it is
--    forced, and this application connects as the owner, so enabling it changes
--    nothing for the backend - it only closes the client roles off further.
DO $do$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT c.oid::regclass AS rel
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', r.rel);
    END LOOP;
END
$do$;

-- 4. What the two client roles still hold, after the change. Every privilege
--    column should read false. The join on pg_roles means a Postgres that has
--    neither role - a local one - simply returns no rows instead of erroring.
SELECT c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       r.rolname AS client_role,
       has_table_privilege(r.rolname, c.oid, 'SELECT') AS can_select,
       has_table_privilege(r.rolname, c.oid, 'INSERT') AS can_insert,
       has_table_privilege(r.rolname, c.oid, 'DELETE') AS can_delete
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles r ON r.rolname IN ('anon', 'authenticated')
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY 1, 3;
