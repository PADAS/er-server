CREATE OR REPLACE FUNCTION get_table_column_and_type(tableName text) 
RETURNS text 
AS
$body$
DECLARE
  schemaName TEXT;
BEGIN
  IF tableName LIKE '%.%' THEN
    schemaName := SPLIT_PART(tableName, '.', 1);
    tableName := SPLIT_PART(tableName, '.', 2);
    
    RETURN (SELECT RTRIM(strings(a.attname || ' ' || pg_catalog.format_type(a.atttypid, a.atttypmod) || ','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                   JOIN pg_namespace ns ON (ns.oid = c.relnamespace AND ns.nspname = schemaName)
                                  WHERE c.relname = tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  ELSE    
    RETURN (SELECT RTRIM(strings(a.attname || ' ' || pg_catalog.format_type(a.atttypid, a.atttypmod) || ','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                  WHERE pg_catalog.pg_table_is_visible(c.oid) 
                                    AND c.relname = tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  END IF;
END;
$body$
LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_table_column_and_type(tableName text, excludeColumns text[]) 
RETURNS text 
AS
$body$
DECLARE
  schemaName TEXT;
BEGIN
  IF tableName LIKE '%.%' THEN
    schemaName := SPLIT_PART(tableName, '.', 1);
    tableName := SPLIT_PART(tableName, '.', 2);
    
    RETURN (SELECT RTRIM(strings(a.attname || ' ' || pg_catalog.format_type(a.atttypid, a.atttypmod) || ','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE NOT a.attname = ANY(excludeColumns)
               AND a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                   JOIN pg_namespace ns ON (ns.oid = c.relnamespace AND ns.nspname = schemaName)
                                  WHERE c.relname = tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  ELSE
    RETURN (SELECT RTRIM(strings(a.attname || ' ' || pg_catalog.format_type(a.atttypid, a.atttypmod) || ','), ',')
              FROM pg_catalog.pg_attribute a
             WHERE NOT a.attname = ANY(excludeColumns)
               AND a.attrelid = (SELECT c.oid 
                                   FROM pg_catalog.pg_class c 
                                  WHERE pg_catalog.pg_table_is_visible(c.oid) 
                                    AND c.relname = tableName
                                 ORDER BY c.oid) 
               AND a.attnum > 0 AND NOT a.attisdropped
            GROUP BY a.attrelid);
  END IF;
END;
$body$
LANGUAGE plpgsql;

