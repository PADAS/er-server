CREATE OR REPLACE FUNCTION get_child_partitions(i_parent_table TEXT)
RETURNS TABLE(child_schema TEXT, child_table_name TEXT)
AS
$body$
  SELECT cs.nspname::TEXT AS child_schema, c.relname::TEXT AS child_table
    FROM pg_class as p
    JOIN pg_inherits as inh ON (inh.inhparent = p.oid)
    JOIN pg_class AS c ON (inh.inhrelid = c.oid)
    JOIN pg_namespace cs ON cs.oid = c.relnamespace
   WHERE p.relname = i_parent_table;
$body$ 
LANGUAGE sql;

