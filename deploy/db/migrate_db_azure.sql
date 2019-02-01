-- For verifying connectivity to us dev databases:
-- psql -h das-postgres-us-azure.postgres.database.azure.com -U postgres@das-postgres-us-azure -d postgres
-- 

-- Clean out the old database
DROP DATABASE IF EXISTS :db_name;
DROP USER IF EXISTS :db_owner;

-- Create the users and the database
CREATE ROLE :db_owner WITH LOGIN NOSUPERUSER INHERIT CREATEDB CREATEROLE NOREPLICATION PASSWORD ':db_passwd';
-- Only azure_pg_admin can add extensions and manipulate schema
ALTER ROLE :db_owner WITH PASSWORD ':db_passwd';
GRANT azure_pg_admin TO :db_owner;
GRANT :db_owner to postgres;
SET ROLE :db_owner;

CREATE DATABASE :db_name ENCODING 'utf8';

-- switch over into the new database
\C :db_name;
