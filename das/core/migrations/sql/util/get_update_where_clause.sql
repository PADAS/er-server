CREATE OR REPLACE FUNCTION get_update_where_clause(i_tablename TEXT, i_excludecolumns TEXT[], i_target_alias TEXT, i_source_alias TEXT)
RETURNS TEXT AS 
$function$
DECLARE
  schema TEXT;
BEGIN
  IF i_tablename LIKE '%.%' THEN
    schema := SPLIT_PART(i_tablename, '.', 1);
    i_tablename := SPLIT_PART(i_tablename, '.', 2);

    RETURN (SELECT '(' || RTRIM(strings(i_target_alias || '.' || a.attname || ' IS DISTINCT FROM '|| i_source_alias || '.' || a.attname || ' OR '), ' OR ') || ')'
              FROM pg_class c
              JOIN pg_namespace ns ON (ns.oid = c.relnamespace AND ns.nspname = schema)
              LEFT JOIN pg_index i ON (i.indrelid = c.oid AND i.indisprimary)
              JOIN pg_attribute a ON (a.attrelid = c.oid AND NOT a.attisdropped AND a.attnum > 0 AND a.attnum != ALL(COALESCE(i.indkey, array[0])) AND a.attname != ALL(COALESCE(i_excludeColumns, ARRAY[''])))
             WHERE c.relname = i_tablename);
  ELSE
    RETURN (SELECT '(' || RTRIM(strings(i_target_alias || '.' || a.attname || ' IS DISTINCT FROM '|| i_source_alias || '.' || a.attname ||' OR '), ' OR ') || ')'
              FROM pg_class c
              LEFT JOIN pg_index i ON (i.indrelid = c.oid AND i.indisprimary )
              JOIN pg_attribute a ON (a.attrelid = c.oid AND NOT a.attisdropped AND a.attnum > 0 AND a.attnum != ALL(COALESCE(i.indkey, array[0])) AND a.attname != ALL(COALESCE(i_excludeColumns, ARRAY[''])))
             WHERE c.relname = i_tablename
               AND pg_table_is_visible(c.oid));
  END IF;
END;
$function$
LANGUAGE plpgsql;
