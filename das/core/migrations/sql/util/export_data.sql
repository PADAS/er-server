CREATE OR REPLACE FUNCTION export_data(i_dblink TEXT, i_table_name TEXT, i_where_clause TEXT) 
RETURNS VOID 
AS
$body$
DECLARE
  temp_str TEXT;
  sql_cmd TEXT;
  start_time TIMESTAMP;
  end_time TIMESTAMP;
BEGIN
  start_time := get_current_time_of_day();
  temp_str := start_time;
  RAISE INFO 'Started at: %', temp_str;
  
  sql_cmd := 'INSERT INTO ' || i_table_name || 
             ' SELECT * FROM dblink(' || (CASE WHEN i_dblink IS NULL THEN '' ELSE quote_literal(i_dblink) || ',' END) || 
             '''SELECT ' || get_table_column(i_table_name) || ' FROM ' || i_table_name || 
             CASE WHEN i_where_clause IS NULL THEN '' ELSE ' WHERE ' || i_where_clause END || ''') AS tab (' ||
             get_table_column_and_type(i_table_name) || ')';

  EXECUTE sql_cmd;
  
  end_time := get_current_time_of_day();
  temp_str := end_time;
  RAISE INFO 'End Time: %', temp_str;
  temp_str := end_time - start_time;
  RAISE INFO 'Total Elapsed Time: %', temp_str; 
END;
$body$ 
LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION export_data(i_dblink TEXT, i_table_name TEXT, i_join_clause TEXT, i_where_clause TEXT, i_timing_on CHAR) 
RETURNS VOID 
AS
$body$
DECLARE
  temp_str TEXT;
  sql_cmd TEXT;
  start_time TIMESTAMP;
  end_time TIMESTAMP;
BEGIN
  IF i_timing_on IN ('y','Y','t','T') THEN
    start_time := get_current_time_of_day();
    temp_str := start_time;
    RAISE INFO 'Started at: %', temp_str;
  END IF;
    
  sql_cmd := 'INSERT INTO ' || i_table_name || 
             ' SELECT * FROM dblink(' || (CASE WHEN i_dblink IS NULL THEN '' ELSE quote_literal(i_dblink) || ',' END) || 
             '''SELECT ' || get_table_column(i_table_name) || ' FROM ' || i_table_name || 
             COALESCE(' ' || i_join_clause, '') ||
             COALESCE(' WHERE ' || i_where_clause, '') || ''') AS tab (' ||
             get_table_column_and_type(i_table_name) || ')';

  EXECUTE sql_cmd;
  
  IF i_timing_on IN ('y','Y','t','T') THEN  
    end_time := get_current_time_of_day();
    temp_str := end_time;
    RAISE INFO 'End Time: %', temp_str;
    temp_str := end_time - start_time;
    RAISE INFO 'Total Elapsed Time: %', temp_str;
  END IF;    
END;
$body$ 
LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION export_data(i_table_name TEXT) 
RETURNS VOID 
AS
$body$
  SELECT export_data(NULL::TEXT, i_table_name, NULL::TEXT);
$body$ 
LANGUAGE sql;

CREATE OR REPLACE FUNCTION export_data(i_table_name TEXT, i_where_clause TEXT) 
RETURNS VOID 
AS
$body$
  SELECT export_data(NULL::TEXT, i_table_name, i_where_clause);
$body$ 
LANGUAGE sql;

