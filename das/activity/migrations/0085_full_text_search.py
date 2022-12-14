# Generated by Django 2.2.9 on 2020-04-07 02:09

from django.db import migrations

ADD_TSVECTOR_COLUMNS = """
 alter table activity_tsvectormodel 
 add column tsvector_event TSVECTOR,
 add column tsvector_event_note TSVECTOR;
"""

INDEX_TSVECTOR_EVENT = """
create index tsvector_event_index on activity_tsvectormodel using gin(tsvector_event);
"""

INDEX_TSVECTOR_EVENTNOTE = """
create index tsvector_eventnote_index on activity_tsvectormodel using gin(tsvector_event_note);
"""

INSERT_TSVECTOR_EVENT = """
INSERT INTO activity_tsvectormodel (event_id, tsvector_event)
SELECT  e.id,
        setweight(to_tsvector(et.display)::tsvector, 'A')|| 
        setweight(to_tsvector(coalesce(e.title,'')), 'B')||
        setweight(to_tsvector(et.schema::text), 'B')||
        setweight(to_tsvector((ed.data#>> '{event_details}')::text), 'A')
 FROM activity_event e join activity_eventtype et on e.event_type_id = et.id join activity_eventdetails ed on e.id = ed.event_id
on conflict do nothing;
"""

UPDATE_TSVECTOR_EVENT_NOTE = """
UPDATE activity_tsvectormodel ts SET (tsvector_event_note) =
    (SELECT to_tsvector(string_agg(text, ','))::tsvector FROM activity_eventnote en
     WHERE  en.event_id= ts.event_id);
"""

TRIGGER_FUNC = """
CREATE OR REPLACE FUNCTION tsvector_doc_trigger() RETURNS trigger as $$
begin
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO activity_tsvectormodel (event_id, tsvector_event)
        SELECT  e.id,  
                setweight(to_tsvector(et.display)::tsvector, 'A')|| 
                setweight(to_tsvector(coalesce(e.title,'')), 'B')||
                setweight(to_tsvector(et.schema::text), 'B')||
                setweight(to_tsvector((ed.data#>> '{event_details}')::text), 'A')
        FROM activity_event e join activity_eventtype et on e.event_type_id = et.id join activity_eventdetails ed on e.id = ed.event_id
          WHERE ed.id = NEW.id
        on conflict do nothing;
    ELSIF (TG_OP = 'UPDATE') THEN
        update activity_tsvectormodel ts set
        tsvector_event =
        setweight(to_tsvector(et.display)::tsvector, 'A')||
        setweight(to_tsvector(coalesce(e.title,'')), 'B')||
        setweight(to_tsvector(et.schema::text), 'B')||
        setweight(to_tsvector((ed.data#>> '{event_details}')::text), 'A')
        from activity_event e, activity_eventtype et, activity_eventdetails ed 
        where e.event_type_id = et.id and ed.event_id = e.id and e.id = ts.event_id
        and ed.id = OLD.id;
    END IF;
    return new;
end
$$ LANGUAGE plpgsql;

CREATE TRIGGER tsvector_update AFTER  INSERT OR UPDATE
on activity_eventdetails
FOR EACH ROW EXECUTE PROCEDURE tsvector_doc_trigger();
"""

TRIGGER_FUNC_EVENTNOTE = """
CREATE OR REPLACE FUNCTION tsvector_eventnote_trigger() RETURNS trigger as $$
begin
    UPDATE activity_tsvectormodel ts SET (tsvector_event_note) =
        (SELECT to_tsvector(string_agg(text, ','))::tsvector FROM activity_eventnote en
         WHERE  en.event_id= ts.event_id 
           AND en.event_id = OLD.event_id);
    return new;
end
$$ LANGUAGE plpgsql;
CREATE TRIGGER tsvector_evennote_update AFTER INSERT OR UPDATE
on activity_eventnote
FOR EACH ROW EXECUTE PROCEDURE tsvector_eventnote_trigger();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0084_tsvector_model'),
    ]

    operations = [
        migrations.RunSQL(ADD_TSVECTOR_COLUMNS,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(INDEX_TSVECTOR_EVENT,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(INDEX_TSVECTOR_EVENTNOTE,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(INSERT_TSVECTOR_EVENT,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(TRIGGER_FUNC,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(UPDATE_TSVECTOR_EVENT_NOTE,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(TRIGGER_FUNC_EVENTNOTE,
                          reverse_sql=migrations.RunSQL.noop)
    ]
