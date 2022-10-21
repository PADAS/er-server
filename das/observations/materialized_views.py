import logging
from django.db import connection

logger = logging.getLogger(__name__)


class PatrolsMaterializedView:

    def __init__(self, table_name):
        self.table_name = table_name
        self.lookback = 30

    @property
    def generate_ddl(self):
        ddl = f"""

        CREATE OR REPLACE FUNCTION to_four_dps(i float) RETURNS float AS $$
            BEGIN RETURN ROUND(i::numeric, 4); END;
        $$ LANGUAGE plpgsql;

        CREATE MATERIALIZED VIEW IF NOT EXISTS {self.table_name} AS
            SELECT p.serial_number as "Patrol Serial Number",
            CASE 
                WHEN p.title NOT LIKE '' THEN p.title
                WHEN ps.leader_id IS NOT NULL THEN (SELECT name FROM observations_subject WHERE id=ps.leader_id)
                ELSE pt.display END
            as "Title",
                
            pt.display as "Patrol Type",
            
            (SELECT name FROM observations_subject WHERE id=ps.leader_id) as "Tracked Subject",
                
            (
              SELECT string_agg(model_name, '/') model_name from 
                  (select distinct(model_name) model_name from observations_source
                     where id = any(select source_id from observations_subjectsource
                                   where subject_id=ps.leader_id
                                     and assigned_range && ps.time_range)) modelnames
                          
            ) as "Tracked Device",
                            
            lower(ps.time_range) AS "Actual Start Date",
            ps.scheduled_start AS "Scheduled Start Date",

            upper(ps.time_range) AS "Actual End Date",
            ps.scheduled_end AS "Scheduled End Date",
                
            to_four_dps(ST_Y(ps.start_location)) as "Start Lat",
            to_four_dps(ST_X(ps.start_location))  as "Start Lon",

            to_four_dps(ST_Y(ps.end_location))  as "End Lat",
            to_four_dps(ST_X(ps.end_location))  as "End Lon",
                
            CASE
                WHEN (p.state='open' AND ps.scheduled_start IS NOT NULL AND ps.scheduled_start >= (NOW() - ('{self.lookback} minute')::INTERVAL)) THEN 'Ready To start'
                WHEN (p.state='open' AND lower(ps.time_range) IS NULL AND ps.scheduled_start IS NOT NULL AND ps.scheduled_start <  (NOW() - ('{self.lookback} minute')::INTERVAL)) THEN 'Start Overdue'
                WHEN (p.state='open' AND ps.time_range IS NOT NULL) THEN 'Active'
                ELSE initcap(p.state) END
            AS "Status",

            to_char(upper(ps.time_range) - lower(ps.time_range), 'DD" days "HH24":"MI":"SS""') as "Duration (hh:mm:ss)",
            
            (SELECT to_four_dps(SUM(patrol_distance)) as "Distance covered (km)" FROM (SELECT
                ASIN(SQRT( POWER(SIN((ST_Y(curr.location) - abs(ST_Y(prev.location))) * pi()/180 / 2),2) 
                  + COS(ST_Y(curr.location) * pi()/180 ) * COS( abs(ST_Y(prev.location)) *  pi()/180) 
                  * POWER(SIN((ST_X(curr.location) - ST_X(prev.location)) * pi()/180 / 2), 2) )) AS patrol_distance

                FROM (SELECT id, location FROM observations_subjectstatus WHERE subject_id=ps.leader_id) prev JOIN 
                    observations_subjectstatus curr ON prev.id = curr.id - 1 WHERE curr.id >= 1) AS "distances"),
            
            p.priority as "Patrol Priority",

            coalesce((select COUNT(event_id) FROM activity_eventrelatedsegments 
                WHERE patrol_segment_id=ps.id GROUP BY patrol_segment_id), 0)as "Number of reports",
            
            (SELECT string_agg(serial_number::text,',')  FROM activity_event WHERE id IN 
                (SELECT event_id FROM activity_eventrelatedsegments WHERE patrol_segment_id = ps.id)) as "Report Serial Numbers",

            NOW() as "Refresh Time"
            
            FROM activity_patrol p INNER JOIN activity_patrolsegment ps  ON  p.id = ps.patrol_id  
                INNER JOIN activity_patroltype pt ON ps.patrol_type_id = pt.id;
        """
        return ddl

    @staticmethod
    def cursor():
        cursor_wrapper = connection.cursor()
        cursor = cursor_wrapper.cursor
        return cursor

    def execute_ddl(self):
        cursor = self.cursor()
        cursor.execute(self.generate_ddl)
        logger.info(f"Successfully created table: {self.table_name}")

    def check_view_exists(self):
        cursor = self.cursor()
        cursor.execute(
            "SELECT to_regclass('public.{0}')".format(self.table_name))
        view_exist = cursor.fetchone()[0]
        return bool(view_exist)

    def refresh_view(self):
        if self.check_view_exists():
            cursor = self.cursor()
            cursor.execute(f"REFRESH MATERIALIZED VIEW {self.table_name}")
            logger.info(f"Succesfully refreshed table: {self.table_name}")
        else:
            self.execute_ddl()

    def drop_view(self):
        cursor = self.cursor()
        cursor.execute(f'DROP MATERIALIZED VIEW IF EXISTS {self.table_name}')
        logger.info(f"{self.table_name} has been deleted.")


patrols_view = PatrolsMaterializedView(table_name='patrols_view')
