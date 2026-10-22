-- Least-privilege database access (plan 4.1: "no DDL at runtime").  NOT YET RUN against Postgres:
-- review it, then run once as the database owner.  Replace the two placeholder passwords first.
--
--   satark_app : what the running API connects as (SATARK_DATABASE_URL). Data access only.
--   owner      : keeps DDL; used only by `alembic upgrade head` via SATARK_MIGRATION_DATABASE_URL.

CREATE ROLE satark_app LOGIN PASSWORD 'REPLACE_WITH_A_GENERATED_PASSWORD'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

-- The app may not create anything in the schema.
-- NOTE: on PostgreSQL 14 and older, PUBLIC (every role) can CREATE in the public schema by default, and revoking
-- from satark_app alone does not remove that. On those versions also run, as the owner:
--   REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- PostgreSQL 15+ (the CI test uses 16) already denies it.
REVOKE ALL ON SCHEMA public FROM satark_app;
GRANT USAGE ON SCHEMA public TO satark_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO satark_app;
-- The app has no business reading or rewriting migration bookkeeping.
REVOKE ALL ON alembic_version FROM satark_app;

-- Tables created by future migrations (run as the owner) get the same grants automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO satark_app;

-- Verify (run as satark_app; each of these must FAIL):
--   CREATE TABLE x (id int);
--   DROP TABLE payments;
--   ALTER TABLE devices ADD COLUMN y int;
--   SELECT * FROM alembic_version;
