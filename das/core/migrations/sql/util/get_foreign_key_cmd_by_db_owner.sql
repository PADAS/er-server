CREATE OR REPLACE FUNCTION get_foreign_key_cmd_by_db_owner(i_database_owner TEXT) 
RETURNS TABLE(drop_fk_cmd TEXT, add_fk_cmd TEXT)
AS
$body$
  SELECT strings(FORMAT('ALTER TABLE %s.%s DROP CONSTRAINT %s; ', n.nspname, c.relname, s.conname) ORDER BY n.nspname, c.relname, s.conname), 
         strings(FORMAT('ALTER TABLE %s.%s ADD CONSTRAINT %s %s; ', n.nspname, c.relname, s.conname, REPLACE(pg_get_constraintdef(s.oid), ' ON DELETE CASCADE', '')) ORDER BY n.nspname, c.relname, s.conname)
    FROM pg_user u
    JOIN pg_namespace n ON (n.nspowner = u.usesysid)
    JOIN pg_class c ON (n.oid = c.relnamespace)
    JOIN pg_constraint s ON (s.conrelid = c.oid and s.contype='f')
   WHERE u.usename = i_database_owner;
$body$                         
LANGUAGE sql;
  