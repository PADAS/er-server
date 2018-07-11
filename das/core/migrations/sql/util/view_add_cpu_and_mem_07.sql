/*
  Administrative and System-viewer Views
*/

/* To see outstanding locks */
CREATE OR REPLACE VIEW public.lock_v AS
select pg_class.relname, pg_locks.transactionid, pg_locks.mode,
       pg_locks.granted as "g", pg_stat_activity.query,
       pg_stat_activity.query_start,
       age(now(),pg_stat_activity.query_start) as "age",
       pg_stat_activity.pid
  from pg_stat_activity, pg_locks
  left outer join pg_class on (pg_locks.relation = pg_class.oid)
 where pg_locks.pid=pg_stat_activity.pid
   and pg_stat_activity.pid != pg_backend_pid()
 order by pg_stat_activity.query_start;

/* To see outstanding queries */
DROP VIEW IF EXISTS public.stat_v;

CREATE OR REPLACE VIEW public.stat_v AS
WITH stats AS (
    SELECT
      pa.pid,
      now() - pa.query_start AS elapsed,
      pa.wait_event,
      pa.query
    FROM pg_stat_activity pa
    WHERE pa.state != 'idle'
          AND pa.pid != pg_backend_pid()
)
SELECT s.pid, s.elapsed, s.wait_event, c.CPU_percent, c.MEM_percent, s.query
  FROM stats s
  LEFT JOIN get_cpu_mem(array_to_string((SELECT array_agg(s2.pid) FROM stats AS s2), ',')) AS c ON (c.pid=s.pid)
;
