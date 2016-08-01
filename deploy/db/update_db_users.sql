
DROP USER IF EXISTS dasdb_owner;
DROP USER IF EXISTS dasdb_user;

CREATE USER dasdb_owner WITH PASSWORD :ownerpw;
CREATE USER dasdb_user WITH PASSWORD :userpw;

ALTER DATABASE :db_name OWNER TO dasdb_owner;

\c :db_name;

REVOKE ALL PRIVILEGES ON DATABASE :db_name FROM public;
GRANT ALL PRIVILEGES ON DATABASE :db_name TO dasdb_owner;
GRANT CONNECT ON DATABASE :db_name TO public;

REVOKE ALL ON schema public FROM public;
GRANT ALL ON schema public TO dasdb_owner;
GRANT USAGE ON SCHEMA public TO public;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO public;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO public;

REVOKE ALL ON schema topology FROM public;
GRANT ALL ON schema topology TO dasdb_owner;
GRANT USAGE ON SCHEMA topology TO public;

GRANT SELECT ON ALL TABLES IN SCHEMA topology TO public;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA topology TO public;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA topology TO public;
