from django.db import connection


class PatrolsMaterializedView:

    def __init__(self, table_name):
        self.table_name = table_name
        self.lookback = 30

    @property
    def generate_ddl(self):
        ddl = f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {self.table_name} AS
            SELECT p.serial_number as "Patrol Serial Number",
            CASE 
                WHEN p.title IS NOT NULL THEN p.title
                WHEN ps.leader_id IS NOT NULL THEN (SELECT name FROM observations_subject WHERE id=ps.leader_id)
                ELSE pt.display END
            as "Title",
                
            pt.display as "Patrol Type",
            
            (SELECT name FROM observations_subject WHERE id=ps.leader_id) as "Tracked Subject",
                
            (SELECT model_name FROM observations_source 
                WHERE id=(SELECT source_id FROM observations_subjectsource 
                    WHERE subject_id=ps.leader_id)) as "Tracked Device",
                
            CASE 
                WHEN ps.time_range IS NOT NULL THEN lower(ps.time_range)
                ELSE ps.scheduled_start END
            AS "Start date",
                
            CASE 
                WHEN ps.time_range IS NOT NULL THEN upper(ps.time_range)
                ELSE ps.scheduled_end END
            AS "End date",
                
            ST_Y(ps.start_location) as "Start Lat",
            ST_X(ps.start_location) as "Start Lon",
            
            ST_Y(ps.end_location) as "End Lat",
            ST_X(ps.end_location) as "End Lon",
                
            CASE
                WHEN (p.state='open' AND ps.scheduled_start IS NOT NULL AND ps.scheduled_start >= (NOW() - ('{self.lookback} minute')::INTERVAL)) THEN 'Ready To start'
                WHEN (p.state='open' AND ps.scheduled_start IS NOT NULL AND ps.scheduled_start <  (NOW() - ('{self.lookback} minute')::INTERVAL)) THEN 'Start Overdue'
                WHEN (p.state='open' AND ps.time_range IS NOT NULL) THEN 'Active'
                ELSE p.state END 
            AS "Status",

            upper(ps.time_range)::timestamp- lower(ps.time_range) as "Duration (hh:mm:ss)",
            
            (SELECT SUM(patrol_distance) as "Distance covered (km)" FROM (SELECT
                ASIN(SQRT( POWER(SIN((ST_Y(curr.location) - abs(ST_Y(prev.location))) * pi()/180 / 2),2) 
                  + COS(ST_Y(curr.location) * pi()/180 ) * COS( abs(ST_Y(prev.location)) *  pi()/180) 
                  * POWER(SIN((ST_X(curr.location) - ST_X(prev.location)) * pi()/180 / 2), 2) )) AS patrol_distance

                FROM (SELECT id, location FROM observations_subjectstatus WHERE subject_id=ps.leader_id) prev JOIN 
                    observations_subjectstatus curr ON prev.id = curr.id - 1 WHERE curr.id >= 1) AS "distances"),
            
            p.priority as "Patrol Priority",

            coalesce((select COUNT(event_id) FROM activity_eventrelatedsegments 
                WHERE patrol_segment_id=ps.id GROUP BY patrol_segment_id), 0)as "Number of reports",
            
            (SELECT ARRAY(SELECT source_id FROM observations_subjectsource WHERE subject_id=ps.leader_id)) as "Tracks",
            
            (SELECT string_agg(event_id::text,',') FROM activity_eventrelatedsegments 
                WHERE patrol_segment_id=ps.id) as "Report IDs"
            
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
        else:
            self.execute_ddl()


patrols_view = PatrolsMaterializedView(table_name='patrols_view')
