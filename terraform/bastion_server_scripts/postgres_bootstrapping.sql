
-- Role assignments --
ALTER ROLE :app_role_name WITH LOGIN;
ALTER ROLE :app_role_name REPLICATION;
ALTER ROLE :migration_role_name WITH LOGIN;
ALTER ROLE :analytics_role_name WITH LOGIN;

-- Give Current User proper roles, particularly to change database ownership.
GRANT :app_role_name, :migration_role_name, :analytics_role_name to current_user;
GRANT :app_user_name, :migration_user_name, :analytics_user_name to current_user;

ALTER DATABASE :db_name OWNER to :app_role_name;

GRANT :app_role_name to :app_user_name WITH ADMIN OPTION;
GRANT :app_role_name, :migration_role_name to :migration_user_name WITH ADMIN OPTION;
GRANT :analytics_role_name to :analytics_user_name;
ALTER ROLE :app_user_name REPLICATION;

-- Temporarily give superpowers to :app_role_name
GRANT cloudsqlsuperuser to :app_role_name;

GRANT CREATE on DATABASE :db_name to :app_role_name, :migration_role_name;
GRANT CONNECT ON DATABASE :db_name TO :analytics_role_name, :app_role_name, :migration_role_name;

-- Create objects using App Role.
-- * The application will run as a User that is granted the App Role.
SET ROLE :app_role_name;

CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "postgis_topology";

-- Grants for various user roles.
GRANT SELECT ON ALL TABLES IN SCHEMA PUBLIC, TOPOLOGY TO :analytics_role_name;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA PUBLIC, TOPOLOGY TO :analytics_role_name;

-- Role statement timeouts
ALTER ROLE :app_role_name SET statement_timeout TO '30s';
ALTER ROLE :migration_role_name SET lock_timeout TO '10s';
ALTER ROLE :analytics_role_name SET statement_timeout TO '3min';

-- Take away superpowers (these were granted by default when terraforming these roles).
REVOKE cloudsqlsuperuser FROM :migration_role_name;
REVOKE cloudsqlsuperuser FROM :migration_user_name;

REVOKE cloudsqlsuperuser FROM :analytics_role_name;
REVOKE cloudsqlsuperuser FROM :analytics_user_name;

REVOKE cloudsqlsuperuser FROM :app_user_name;
REVOKE cloudsqlsuperuser FROM :app_role_name;

-- Switch to app user, to allow altering default privileges.
SET ROLE :app_user_name;
ALTER DEFAULT PRIVILEGES FOR ROLE :app_user_name IN SCHEMA public, topology GRANT ALL PRIVILEGES ON TABLES TO :app_role_name, :migration_role_name WITH GRANT OPTION;
ALTER DEFAULT PRIVILEGES FOR ROLE :app_user_name IN SCHEMA public, topology GRANT ALL PRIVILEGES ON SEQUENCES TO :app_role_name, :migration_role_name WITH GRANT OPTION;
ALTER DEFAULT PRIVILEGES FOR ROLE :app_user_name IN SCHEMA public, topology GRANT SELECT ON TABLES TO :analytics_role_name;
ALTER DEFAULT PRIVILEGES FOR ROLE :app_user_name IN SCHEMA public, topology GRANT USAGE, SELECT ON SEQUENCES TO :analytics_role_name;
