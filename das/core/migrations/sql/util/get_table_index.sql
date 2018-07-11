CREATE OR REPLACE FUNCTION get_table_index(i_schema TEXT, i_table_name TEXT) 
RETURNS TABLE(index_name TEXT, is_primary BOOLEAN, index_create TEXT)
AS
$body$
  select ic.relname::TEXT, indisprimary, pg_get_indexdef(i.indexrelid)::TEXT
    from pg_namespace ns
    join pg_class c on (c.relnamespace = ns.oid)
    join pg_index i on (i.indrelid = c.oid)
    join pg_class ic on (ic.oid = i.indexrelid)
   where ns.nspname = i_schema 
     and c.relname = i_table_name;
$body$ 
LANGUAGE sql;

