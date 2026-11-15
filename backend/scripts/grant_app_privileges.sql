-- Least-privilege access for the RUNNING application (psql variables: db, owner, app).
-- Run by scripts/setup_least_privilege.sh as the PostgreSQL superuser. Safe to run again (e.g. after new migrations).
--
-- The owner (used only by `alembic`) keeps full control. The app user can read and change rows, but can't:
--   create, alter or drop tables;   change or delete audit records;   change the permission catalogue or migration state.
\set ON_ERROR_STOP on

REVOKE CONNECT, TEMPORARY ON DATABASE :"db" FROM PUBLIC;   -- only users we name may connect at all
GRANT CONNECT ON DATABASE :"db" TO :"app";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;                -- nobody but the owner creates objects (PostgreSQL 15+ default)
GRANT USAGE ON SCHEMA public TO :"app";

-- Ordinary data: read and write rows. (No TRUNCATE, no REFERENCES, no TRIGGER, no DDL.)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"app";  -- UPDATE: the dev-only demo reset restarts IDs

-- Append-only audit log: add and read, never change or delete (the trigger also refuses, this is a second wall).
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM :"app";
-- Written only by migrations.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON permissions, alembic_version FROM :"app";

-- Tables created by FUTURE migrations (owned by the owner) get ordinary row access automatically.
-- Re-run this script after migrations that add special tables like the audit log.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app";
