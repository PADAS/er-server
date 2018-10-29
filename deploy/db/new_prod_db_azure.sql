-- For us dev databases:
-- psql -h das-postgres-us-azure.postgres.database.azure.com -U postgres@das-postgres-us-azure -d postgres
-- 

-- Set db_admin and db_user
dasdb_owner := :db_name || 'owner'
dasdb_user := :db_user || 'user'

-- Clean out the old database
DROP DATABASE IF EXISTS :db_name;
DROP USER IF EXISTS :dasdb_owner;
DROP USER IF EXISTS :dasdb_user;

-- Create the users and the database
CREATE USER :dasdb_owner WITH PASSWORD :owner_pwd;
CREATE USER :dasdb_user WITH PASSWORD :user_pwd;
CREATE DATABASE :db_name ENCODING 'utf8' OWNER :dasdb_owner;

-- switch over into the new database
\c :db_name;

-- Update permissions for admin and "read-only" users
REVOKE ALL PRIVILEGES ON DATABASE :db_name FROM public;
GRANT ALL PRIVILEGES ON DATABASE :db_name TO :dasdb_owner;
GRANT CONNECT ON DATABASE :db_name TO public;

REVOKE ALL ON schema public FROM public;
GRANT ALL ON schema public TO :dasdb_owner;
GRANT USAGE ON SCHEMA public TO public;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO public;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO public;

-- Now install postgis and do the rest of the configuration
CREATE EXTENSION postgis;
CREATE EXTENSION postgis_topology;

-- Update permissions on topology schema
REVOKE ALL ON schema topology FROM public;
GRANT ALL ON schema topology TO :dasdb_owner;
GRANT USAGE ON SCHEMA topology TO public;

GRANT SELECT ON ALL TABLES IN SCHEMA topology TO public;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA topology TO public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA topology TO public;
