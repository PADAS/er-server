CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "postgis_topology";

-- Revoke new user access and table creation in public schema
REVOKE ALL ON DATABASE :db_owner FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
