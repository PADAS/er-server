/*
  Administrative and System-viewer Views
*/

CREATE OR REPLACE FUNCTION public.schema_v(i_schema TEXT) 
RETURNS TABLE(table_name TEXT, row_count TEXT, disk_size TEXT, ds_raw BIGINT, disk_pages TEXT) AS
$body$
  SELECT tables.relname::TEXT, 
         to_char(tables.measurements[1], '999,999,999,999'::text), 
         pg_size_pretty(tables.measurements[2]), 
         tables.measurements[2], 
         to_char(tables.measurements[3], '999,999,999,999'::text) 
    FROM (SELECT c.relname, ARRAY[(c.reltuples)::bigint, pg_relation_size(c.oid), (c.relpages)::bigint] AS measurements 
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'r' 
          UNION ALL 
          SELECT 'TOTALS: ' AS relname, ARRAY[(sum(c.reltuples))::bigint, (sum(pg_relation_size(c.oid)))::bigint, sum(c.relpages)] AS measurements 
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'r') tables 
   ORDER BY CASE WHEN tables.relname = 'TOTALS: ' THEN (-1)::bigint ELSE tables.measurements[1] END DESC, tables.relname;
$body$
LANGUAGE sql;

CREATE OR REPLACE FUNCTION public.schema_v(i_schema TEXT, i_relkind TEXT[]) 
RETURNS TABLE(object_type TEXT, object_name TEXT) AS
$body$
  SELECT (CASE relkind WHEN 'r' THEN 'TABLE' WHEN 'v' THEN 'VIEW' WHEN 'S' THEN 'SEQUENCE' WHEN 'i' THEN 'INDEX' WHEN 'c' THEN 'COMPOSITE TYPE' WHEN 't' THEN 'TOAST' END),
         (nspname || '.' || relname)
    FROM pg_class c 
    JOIN pg_namespace n ON (c.relnamespace = n.oid) 
   WHERE nspname = i_schema 
     AND relkind = ANY(i_relkind) 
   ORDER BY relkind = 'S', relname;
$body$
LANGUAGE sql;

CREATE OR REPLACE FUNCTION public.index_v(i_schema TEXT) 
RETURNS TABLE(index_name TEXT, table_space TEXT, table_name TEXT, row_count TEXT, disk_size TEXT, ds_raw BIGINT, disk_pages TEXT) AS
$body$
  SELECT tables.relname::TEXT,
         tables.tablespace::TEXT,
         tables.tablename::TEXT,
         to_char(tables.measurements[1], '999,999,999,999'::text),
         pg_size_pretty(tables.measurements[2]), 
         tables.measurements[2],
         to_char(tables.measurements[3], '999,999,999,999'::text) 
    FROM (SELECT c.relname, i.tablespace, i.tablename, ARRAY[(c.reltuples)::bigint, pg_relation_size(c.oid), (c.relpages)::bigint] AS measurements 
            FROM pg_class c, pg_indexes i 
           WHERE c.relname = i.indexname AND i.schemaname = $1 
          UNION ALL 
          SELECT 'TOTALS: ' AS relname, '' AS tablespace, '' AS tablename, ARRAY[(sum(c.reltuples))::bigint, (sum(pg_relation_size(c.oid)))::bigint, sum(c.relpages)] AS measurements 
            FROM pg_class c, pg_indexes i 
           WHERE c.relname = i.indexname AND i.schemaname = $1) tables 
  ORDER BY CASE WHEN tables.relname = 'TOTALS: ' THEN (-1)::bigint ELSE tables.measurements[1] END DESC, tables.relname;
$body$
LANGUAGE sql;

CREATE OR REPLACE FUNCTION public.view_v(i_schema TEXT) 
RETURNS TABLE(table_name TEXT, row_count TEXT, disk_size TEXT, ds_raw BIGINT, disk_pages TEXT) AS
$body$
  SELECT tables.relname::TEXT, 
         to_char(tables.measurements[1], '999,999,999,999'::text), 
         pg_size_pretty(tables.measurements[2]), 
         tables.measurements[2], 
         to_char(tables.measurements[3], '999,999,999,999'::text) 
    FROM (SELECT c.relname, ARRAY[(c.reltuples)::bigint, pg_relation_size(c.oid), (c.relpages)::bigint] AS measurements 
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'v' 
          UNION ALL 
          SELECT 'TOTALS: ' AS relname, ARRAY[(sum(c.reltuples))::bigint, (sum(pg_relation_size(c.oid)))::bigint, sum(c.relpages)] AS measurements 
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'v') tables 
   ORDER BY CASE WHEN tables.relname = 'TOTALS: ' THEN (-1)::bigint ELSE tables.measurements[1] END DESC, tables.relname;
$body$
LANGUAGE sql;

CREATE OR REPLACE FUNCTION public.matview_v(i_schema TEXT) 
RETURNS TABLE(table_name TEXT, row_count TEXT, disk_size TEXT, ds_raw BIGINT, disk_pages TEXT) AS
$body$
  SELECT tables.relname::TEXT, 
         to_char(tables.measurements[1], '999,999,999,999'::text), 
         pg_size_pretty(tables.measurements[2]), 
         tables.measurements[2], 
         to_char(tables.measurements[3], '999,999,999,999'::text) 
    FROM (SELECT c.relname, ARRAY[(c.reltuples)::bigint, pg_relation_size(c.oid), (c.relpages)::bigint] AS measurements 
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'm' 
          UNION ALL 
          SELECT 'TOTALS: ' AS relname, ARRAY[(sum(c.reltuples))::bigint, (sum(pg_relation_size(c.oid)))::bigint, sum(c.relpages)] AS measurements 
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'm') tables 
   ORDER BY CASE WHEN tables.relname = 'TOTALS: ' THEN (-1)::bigint ELSE tables.measurements[1] END DESC, tables.relname;
$body$
LANGUAGE sql;

CREATE OR REPLACE FUNCTION public.schema_by_dependency_v(i_schema TEXT) 
RETURNS TABLE(table_name TEXT, row_count TEXT, disk_size TEXT, ds_raw BIGINT, disk_pages TEXT, parent TEXT[], children TEXT[]) AS
$body$
  SELECT tables.relname::TEXT, 
         to_char(tables.measurements[1], '999,999,999,999'::text), 
         pg_size_pretty(tables.measurements[2]), 
         tables.measurements[2], 
         to_char(tables.measurements[3], '999,999,999,999'::text),
         parent,
         children
    FROM (SELECT c.relname, ARRAY[(c.reltuples)::bigint, pg_relation_size(c.oid), (c.relpages)::bigint] AS measurements,
                 (SELECT ARRAY_AGG(p.relname::TEXT) FROM pg_catalog.pg_constraint r, pg_class p WHERE r.conrelid = c.oid AND r.contype = 'f' AND p.oid = r.confrelid) AS parent,
                 (SELECT ARRAY_AGG(p.relname::TEXT) FROM pg_catalog.pg_constraint r, pg_class p WHERE r.confrelid = c.oid AND r.contype = 'f' AND p.oid = r.conrelid) AS children
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'r' 
          UNION ALL 
          SELECT 'TOTALS: ' AS relname, ARRAY[(sum(c.reltuples))::bigint, (sum(pg_relation_size(c.oid)))::bigint, sum(c.relpages)] AS measurements, NULL::TEXT[], NULL::TEXT[]
            FROM pg_class c, pg_namespace n 
           WHERE c.relnamespace = n.oid AND n.nspname = $1 AND c.relkind = 'r') tables 
   ORDER BY CASE WHEN tables.relname = 'TOTALS: ' THEN (-1)::bigint ELSE tables.measurements[1] END DESC, tables.relname;
$body$
LANGUAGE sql;

CREATE OR REPLACE FUNCTION public.function_v(i_schema TEXT, i_table_name TEXT) 
RETURNS TEXT AS
$body$
  SELECT
      routine_definition 
  FROM
      information_schema.routines 
  WHERE
      specific_schema = $1
      AND routine_name = $2;
$body$
LANGUAGE sql;

/* To see outstanding locks */
CREATE OR REPLACE VIEW public.lock_v AS
select pg_class.relname, pg_locks.transactionid, pg_locks.mode,
       pg_locks.granted as "g", pg_stat_activity.query,
       pg_stat_activity.query_start,
       age(now(),pg_stat_activity.query_start) as "age",
       pg_stat_activity.pid
from pg_stat_activity,pg_locks
left outer join pg_class on (pg_locks.relation = pg_class.oid)
where pg_locks.pid=pg_stat_activity.pid
order by query_start;

/* To see outstanding queries */
CREATE OR REPLACE VIEW public.stat_v AS
SELECT pa.pid, 
       now() - pa.query_start AS elapsed,
       pa.wait_event,
       pa.query
  FROM pg_stat_activity pa
 WHERE pa.state != 'idle'
   AND pa.pid != pg_backend_pid();

