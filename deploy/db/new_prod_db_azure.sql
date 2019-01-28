-- For verifying connectivity to us dev databases:
-- psql -h das-postgres-us-azure.postgres.database.azure.com -U postgres@das-postgres-us-azure -d postgres
-- 

-- Clean out the old database
DROP DATABASE IF EXISTS :db_name;
DROP USER IF EXISTS :db_owner;

-- Create the users and the database
CREATE ROLE :db_owner WITH LOGIN NOSUPERUSER INHERIT CREATEDB CREATEROLE NOREPLICATION PASSWORD ':db_passwd';
-- Only azure_pg_admin can add extensions and manipulate schema
GRANT azure_pg_admin TO :db_owner;
GRANT :db_owner to postgres;
SET ROLE :db_owner;

CREATE DATABASE :db_name ENCODING 'utf8';

-- switch over into the new database
\C :db_name;

-- Update permissions for admin and "read-only" users
REVOKE ALL PRIVILEGES ON DATABASE :db_name FROM public;
GRANT ALL PRIVILEGES ON DATABASE :db_name TO :db_owner;
GRANT CONNECT ON DATABASE :db_name TO public;

REVOKE ALL ON schema public FROM public;
GRANT ALL ON schema public TO :db_owner;
GRANT USAGE ON SCHEMA public TO public;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO public;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO public;

-- Now install postgis and do the rest of the configuration
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Update permissions on topology schema
REVOKE ALL ON schema topology FROM public;
GRANT ALL ON schema topology TO :db_owner;
GRANT USAGE ON SCHEMA topology TO public;

GRANT SELECT ON ALL TABLES IN SCHEMA topology TO public;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA topology TO public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA topology TO public;
