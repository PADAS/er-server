CREATE OR REPLACE FUNCTION get_table_foreign_key(i_schema TEXT, i_table_name TEXT) 
RETURNS TABLE(drop_fk_cmd TEXT, add_fk_cmd TEXT)
AS
$body$
  SELECT strings(FORMAT('ALTER TABLE %s.%s DROP CONSTRAINT %s; ', n.nspname, c.relname, s.conname) ORDER BY n.nspname, c.relname, s.conname), 
         strings(FORMAT('ALTER TABLE %s.%s ADD CONSTRAINT %s %s; ', n.nspname, c.relname, s.conname, REPLACE(pg_get_constraintdef(s.oid), ' ON DELETE CASCADE', '')) ORDER BY n.nspname, c.relname, s.conname)
    FROM pg_constraint AS s
    JOIN pg_class AS c ON (c.oid = s.conrelid AND c.relname = i_table_name)
    JOIN pg_namespace as n ON (n.oid = c.relnamespace AND n.nspname = i_schema)
   WHERE s.contype = 'f';
$body$                         
LANGUAGE sql;
  