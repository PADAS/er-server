/*
  Upgrade script to change django user from auth_user to accounts_user

  run with psql

  psql -h 127.0.0.1 -d das_devdb -U postgres -l -f .\0001.sql --set ON_ERROR_STOP=1

  after running, safe to move migration through level 1
  >python manage.py migrate accounts 0001 --fake

  Then need to go through level 2 to add table permissionset
 */

CREATE OR REPLACE FUNCTION pg_temp.rem_constraint(x_table TEXT, x_column TEXT, x_like TEXT) RETURNS void AS $$
DECLARE
  the_constraint_name text;
  index_names record;
BEGIN
  SELECT CONSTRAINT_NAME INTO the_constraint_name
    FROM information_schema.constraint_column_usage
    WHERE CONSTRAINT_SCHEMA = current_schema()
        AND COLUMN_NAME IN (x_column)
        AND TABLE_NAME = x_table
    GROUP BY CONSTRAINT_NAME
    HAVING count(*) = 1;
    if the_constraint_name is not NULL then
        RAISE notice 'alter table % drop constraint %',
            x_table,
            the_constraint_name;
        execute 'alter table ' || x_table
            || ' drop constraint ' || the_constraint_name;
    end if;

    SELECT CONSTRAINT_NAME INTO the_constraint_name
    FROM information_schema.constraint_column_usage
    WHERE CONSTRAINT_SCHEMA = current_schema()
        AND COLUMN_NAME IN ('id')
        AND TABLE_NAME = 'auth_user'
        AND CONSTRAINT_NAME LIKE x_like
    GROUP BY CONSTRAINT_NAME
    HAVING count(*) = 1;
    if the_constraint_name is not NULL then
        RAISE notice 'alter table % drop constraint %',
            x_table,
            the_constraint_name;
        execute 'alter table ' || x_table
            || ' drop constraint ' || the_constraint_name;
    end if;

    FOR index_names IN
    (SELECT i.relname AS index_name
     FROM pg_class t,
          pg_class i,
          pg_index ix,
          pg_attribute a
     WHERE t.oid = ix.indrelid
         AND i.oid = ix.indexrelid
         AND a.attrelid = t.oid
         AND a.attnum = any(ix.indkey)
         AND t.relkind = 'r'
         AND a.attname = x_column
         AND t.relname = x_table
     ORDER BY t.relname,
              i.relname)
    LOOP
        RAISE notice 'drop index %', quote_ident(index_names.index_name);
        EXECUTE 'drop index ' || quote_ident(index_names.index_name);
    END LOOP; -- index_names
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pg_temp.update_id(x_table TEXT, x_column TEXT) RETURNS void AS $$
DECLARE
  recs RECORD;
BEGIN
  EXECUTE 'ALTER TABLE ' || x_table || ' ADD COLUMN user_id_uuid uuid';
  FOR recs in SELECT * FROM accounts_user LOOP
    EXECUTE 'UPDATE ' || x_table || ' SET user_id_uuid =''' || recs.id_uuid || '''::uuid WHERE ' || x_column || '=' || recs.id;
  END LOOP;
  EXECUTE 'ALTER TABLE ' || x_table || ' DROP COLUMN ' || x_column;
  EXECUTE 'ALTER TABLE ' || x_table || ' RENAME COLUMN user_id_uuid TO ' || x_column;
  if x_table != 'activity_event' AND x_table != 'oauth2_provider_accesstoken' THEN
    EXECUTE 'ALTER TABLE ' || x_table || ' ALTER COLUMN ' || x_column || ' SET NOT NULL';
  end if;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pg_temp.add_constraints(x_table TEXT, x_column TEXT) RETURNS void AS $$
BEGIN
  EXECUTE 'ALTER TABLE ' || x_table ||
          ' ADD CONSTRAINT accounts_user_' || x_table ||'_801cd_fk_accounts_user_id'
          ' FOREIGN KEY (' || x_column || ') REFERENCES accounts_user (id) MATCH SIMPLE ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED';
  EXECUTE 'CREATE INDEX ' || x_table || '_e8701ad4 ON ' || x_table || ' (' || x_column ||')';
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
  table_names text[];
  ttn text[];
BEGIN

  table_names := array[
    ['activity_event', 'created_by_user_id', 'activity_event%'],
    ['django_admin_log', 'user_id', 'django_admin_log%'],
    ['oauth2_provider_grant', 'user_id', 'oauth2_provider_grant%'],
    ['oauth2_provider_refreshtoken', 'user_id', 'oauth2_provider_refres%'],
    ['oauth2_provider_application', 'user_id', 'oauth2_provider_applic'],
    ['oauth2_provider_accesstoken', 'user_id', 'oauth2_provider_access']
             ];

DROP TABLE IF EXISTS auth_user_groups CASCADE;
DROP TABLE IF EXISTS auth_user_user_permissions CASCADE;

  FOREACH ttn slice 1 in ARRAY table_names
  LOOP
    RAISE notice 'table row %', ttn;
    PERFORM pg_temp.rem_constraint(ttn[1], ttn[2], ttn[3]);
  END LOOP;

ALTER TABLE auth_user DROP CONSTRAINT auth_user_username_key;
ALTER TABLE auth_user RENAME TO accounts_user;
ALTER TABLE accounts_user ADD COLUMN id_uuid uuid DEFAULT md5(random()::text || clock_timestamp()::text)::uuid;
ALTER TABLE accounts_user ADD COLUMN phone character varying(15) NOT NULL DEFAULT '';
ALTER TABLE accounts_user ADD COLUMN is_email_alert boolean NOT NULL DEFAULT FALSE;
ALTER TABLE accounts_user ADD COLUMN is_sms_alert boolean NOT NULL DEFAULT FALSE;

  FOREACH ttn slice 1 in ARRAY table_names
  LOOP
    RAISE notice 'table row %', ttn;
    PERFORM pg_temp.update_id(ttn[1], ttn[2]);
  END LOOP;

ALTER TABLE accounts_user ALTER COLUMN id_uuid SET NOT NULL;
ALTER TABLE accounts_user DROP CONSTRAINT auth_user_pkey;
ALTER TABLE accounts_user DROP COLUMN id;
ALTER TABLE accounts_user RENAME COLUMN id_uuid TO id;
ALTER TABLE accounts_user ADD PRIMARY KEY (id);
ALTER TABLE accounts_user ADD CONSTRAINT accounts_user_username_key UNIQUE(username);

  FOREACH ttn slice 1 in ARRAY table_names
  LOOP
    PERFORM pg_temp.add_constraints(ttn[1], ttn[2]);
  END LOOP;

ALTER TABLE accounts_user ALTER COLUMN id DROP DEFAULT;
ALTER TABLE accounts_user ALTER COLUMN phone DROP DEFAULT;
ALTER TABLE accounts_user ALTER COLUMN is_email_alert DROP DEFAULT;
ALTER TABLE accounts_user ALTER COLUMN is_sms_alert DROP DEFAULT;

IF EXISTS(SELECT 1 FROM django_content_type WHERE app_label='auth' AND model='user') THEN
    UPDATE django_content_type SET app_label='accounts' WHERE app_label='auth' AND model='user';
END IF;

END;
$$ LANGUAGE plpgsql;


