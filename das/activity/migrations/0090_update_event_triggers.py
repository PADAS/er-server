# Generated by Django 2.2.11 on 2020-05-29 16:43

from django.db import migrations


SQL_FUNC_TSVECTOR_DOC_TRIGGER = """
CREATE OR REPLACE FUNCTION tsvector_doc_trigger() RETURNS trigger as $$
begin
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO activity_tsvectormodel (id, event_id, tsvector_event)
        SELECT  uuid_generate_v4(),
                e.id,  
                setweight(to_tsvector(et.display)::tsvector, 'A')|| 
                setweight(to_tsvector(coalesce(e.title,'')), 'B')||
                setweight(to_tsvector(et.schema::text), 'B')||
                setweight(to_tsvector((ed.data#>> '{event_details}')::text), 'A')
        FROM activity_event e 
              join activity_eventtype et on e.event_type_id = et.id 
              join activity_eventdetails ed on e.id = ed.event_id
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
        where e.event_type_id = et.id 
          and ed.event_id = e.id
          and e.id = ts.event_id
          AND ed.id = NEW.id;
    END IF;
    return new;
end
$$ LANGUAGE plpgsql;
"""

SQL_FUNC_EVENTNOTE_TRIGGER = """
CREATE OR REPLACE FUNCTION tsvector_eventnote_trigger() RETURNS trigger as $$
begin
    UPDATE activity_tsvectormodel ts SET (tsvector_event_note) =
        (SELECT to_tsvector(string_agg(text, ','))::tsvector FROM activity_eventnote en
         WHERE  en.event_id= ts.event_id 
           AND en.event_id = NEW.event_id); 
    return new;
end
$$ LANGUAGE plpgsql;
"""

SQL_FUNC_EVENT_TITLE_TRIGGER = """
CREATE OR REPLACE FUNCTION tsvector_event_title_trigger() RETURNS trigger as $$
begin
    update activity_tsvectormodel ts set
        tsvector_event =
        setweight(to_tsvector(et.display)::tsvector, 'A')||
        setweight(to_tsvector(coalesce(e.title,'')), 'B')||
        setweight(to_tsvector(et.schema::text), 'B')||
        setweight(to_tsvector((ed.data#>> '{event_details}')::text), 'A')
        from activity_event e, activity_eventtype et, activity_eventdetails ed 
        where e.event_type_id = et.id 
          and ed.event_id = e.id 
          and e.id = ts.event_id
          and e.id = NEW.id;
    return new;
end
$$ LANGUAGE plpgsql;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0089_default_vector_id'),
    ]

    operations = [
        migrations.RunSQL(SQL_FUNC_TSVECTOR_DOC_TRIGGER, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(SQL_FUNC_EVENTNOTE_TRIGGER, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(SQL_FUNC_EVENT_TITLE_TRIGGER, reverse_sql=migrations.RunSQL.noop),
    ]