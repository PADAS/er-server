CREATE OR REPLACE FUNCTION get_primary_key_where_clause(i_tablename text, i_target_alias text, i_source_alias text)
RETURNS text AS 
$function$
DECLARE
  schema TEXT;
BEGIN
  IF i_tablename LIKE '%.%' THEN
    schema := SPLIT_PART(i_tablename, '.', 1);
    i_tablename := SPLIT_PART(i_tablename, '.', 2);

    RETURN (SELECT RTRIM(strings(i_target_alias || '.' || a.attname || '='||i_source_alias ||'.'||a.attname ||' AND '), ' AND ')
              FROM pg_class c
              JOIN pg_namespace ns ON (ns.oid = c.relnamespace AND ns.nspname = schema)
              JOIN pg_index i ON (i.indrelid = c.oid AND i.indisprimary) 
              JOIN pg_attribute a ON (a.attrelid = c.oid AND a.attnum = ANY(i.indkey))
             WHERE c.relname = i_tableName);
  ELSE
    RETURN (SELECT RTRIM(strings(i_target_alias || '.' || a.attname || '='||i_source_alias ||'.'||a.attname ||' AND '), ' AND ')
              FROM pg_class c
              JOIN pg_index i ON (i.indrelid = c.oid AND i.indisprimary) 
              JOIN pg_attribute a ON (a.attrelid = c.oid AND a.attnum = ANY(i.indkey))
             WHERE c.relname = i_tableName
               AND pg_table_is_visible(c.oid));
  END IF;
END;
$function$
LANGUAGE plpgsql;

