CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "postgis_topology";

-- Revoke all user access and table creation in public schema in new database
REVOKE ALL ON DATABASE :db_name FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Create Groups - Easier to rotate credentials this way

-- Setup Migrations Group --
-- Group to manage the schema
CREATE ROLE migrations;
GRANT CONNECT ON DATABASE :db_name TO migrations;
GRANT ALL ON SCHEMA public TO migrations;
ALTER ROLE migrations SET lock_timeout TO '10s';

-- Setup user in app group
CREATE ROLE :migrator WITH LOGIN ENCRYPTED PASSWORD :migrator_pass IN ROLE migrations;
ALTER ROLE :migrator SET role TO 'migrations';

-- Apps Group For App using the database
-- Read and write data but shouldn’t need to modify the schema or truncate tables
-- Statement timeout to prevent long running queries from degrading database performance ( Increase if needed)
CREATE ROLE app;
GRANT CONNECT ON DATABASE :db_name TO app;
GRANT USAGE ON SCHEMA public TO app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;
GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE migrations IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE migrations IN SCHEMA public GRANT SELECT, USAGE ON SEQUENCES TO app;
ALTER ROLE app SET statement_timeout TO '30s';

-- Setup user in app group
CREATE ROLE :app_user WITH LOGIN ENCRYPTED PASSWORD :app_user_pass IN ROLE app;

-- Setup Migrations Group --
CREATE ROLE migrations;
GRANT CONNECT ON DATABASE :db_name TO migrations;
GRANT ALL ON SCHEMA public TO migrations;
ALTER ROLE migrations SET lock_timeout TO '10s';

-- Setup Migrations User
CREATE ROLE :migrator WITH LOGIN ENCRYPTED PASSWORD :migrator_pass IN ROLE migrations;
ALTER ROLE :migrator SET role TO 'migrations';

-- Setup Analytics Group

CREATE ROLE analytics;
GRANT CONNECT ON DATABASE :db_name TO analytics;
GRANT USAGE ON SCHEMA public TO analytics;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics;
ALTER DEFAULT PRIVILEGES FOR ROLE migrations IN SCHEMA public GRANT SELECT ON TABLES TO analytics;
ALTER ROLE analytics SET statement_timeout TO '3min';

-- Setup Analytics User
CREATE ROLE :analytics_user WITH LOGIN ENCRYPTED PASSWORD :analytics_user_pass IN ROLE analytics;
