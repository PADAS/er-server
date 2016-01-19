ALTER TABLE IF EXISTS auth_user RENAME accounts_user;
ALTER TABLE IF EXISTS auth_user_groups RENAME accounts_user_groups;
ALTER TABLE IF EXISTS auth_user_user_permissions RENAME accounts_user_user_permissions;
ALTER TABLE accounts_user ADD COLUMN id_uuid uuid DEFAULT uuid_in(md5(random()::text || clock_timestamp()::text));
ALTER TABLE accounts_user_groups ADD COLUMN user_id_uuid uuid;
ALTER TABLE accounts_user_user_permissions ADD COLUMN user_id_uuid uuid;

DO $$
DECLARE
  recs RECORD;
BEGIN
  FOR recs in SELECT * FROM accounts_user LOOP
    EXECUTE 'UPDATE accounts_user_groups SET user_id_uuid =' || recs.id_uuid;
    EXECUTE 'UPDATE accounts_user_user_permissions SET user_id_uuid =' || recs.id_uuid;
  END LOOP;

END;
$$ LANGUAGE plpgsql;




ALTER TABLE accounts_user_groups ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE accounts_user_user_permissions ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE accounts_user ALTER COLUMN id_uuid SET NOT NULL;
ALTER TABLE accounts_user DROP CONSTRAINT accounts_user_pkey;
ALTER TABLE accounts_user DROP COLUMN id;
ALTER TABLE accounts_user RENAME COLUMN id_uuid TO id;
ALTER TABLE accounts_user ADD PRIMARY KEY (id);



DO $$
BEGIN
IF EXISTS(SELECT 1 FROM django_content_type WHERE app_label='auth' AND model='user') THEN
    UPDATE django_content_type SET app_label='accounts' WHERE app_label='auth' AND model='user';
END IF;

END;
$$ LANGUAGE plpgsql;