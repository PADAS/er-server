CREATE OR REPLACE FUNCTION get_update_table_columns(i_tableName text, i_alias TEXT) 
RETURNS text 
AS
$body$
DECLARE
  schemaName TEXT;
BEGIN
  IF i_tableName LIKE '%.%' THEN
    schemaName := SPLIT_PART(i_tableName, '.', 1);
    i_tableName := SPLIT_PART(i_tableName, '.', 2);
    
    RETURN (SELECT RTRIM(strings(a.attname || '='||i_alias ||'.'||a.attname ||','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                   JOIN pg_namespace ns ON (ns.oid = c.relnamespace AND ns.nspname = schemaName)
                                  WHERE c.relname = i_tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  ELSE
    RETURN (SELECT RTRIM(strings(a.attname || '='||i_alias ||'.'||a.attname ||','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                  WHERE pg_catalog.pg_table_is_visible(c.oid) 
                                    AND c.relname = i_tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  END IF;
END;
$body$
LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_update_table_columns(i_tableName text, i_excludeColumns text[], i_alias TEXT) 
RETURNS text 
AS
$body$
DECLARE
  schemaName TEXT;
BEGIN
  IF i_tableName LIKE '%.%' THEN
    schemaName := SPLIT_PART(i_tableName, '.', 1);
    i_tableName := SPLIT_PART(i_tableName, '.', 2);
    
    RETURN (SELECT RTRIM(strings(a.attname || '='||i_alias ||'.'||a.attname ||','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE NOT a.attname = ANY(i_excludeColumns)
               AND a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                   JOIN pg_namespace ns ON (ns.oid = c.relnamespace AND ns.nspname = schemaName)
                                  WHERE c.relname = i_tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  ELSE  
    RETURN (SELECT RTRIM(strings(a.attname || '='||i_alias ||'.'||a.attname ||','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE NOT a.attname = ANY(i_excludeColumns)
               AND a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                  WHERE pg_catalog.pg_table_is_visible(c.oid) 
                                    AND c.relname = i_tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  END IF;
END;
$body$
LANGUAGE plpgsql;

