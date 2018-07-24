CREATE OR REPLACE FUNCTION get_table_check_constraint(tableName text)
RETURNS text
AS
$body$
  SELECT s.consrc
    FROM pg_constraint s, pg_class c
   WHERE s.conrelid = c.oid
     AND c.relname = tableName
     AND s.conname ~ 'check';
$body$
LANGUAGE sql;

