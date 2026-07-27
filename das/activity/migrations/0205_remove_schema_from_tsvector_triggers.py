"""ERA-13500: stop indexing the event type's JSON schema into ``tsvector_event``.

``tsvector_doc_trigger`` (0155) and ``tsvector_event_title_trigger`` (0156) both
folded ``setweight(to_tsvector(et.schema::text), 'B')`` into the event's search
vector. That serializes the *whole* event type schema, so every choice
label/value the schema can offer became searchable text on every event of that
type -- searching for one rhino's name returned sightings of every other
individual defined in the schema.

These ``CREATE OR REPLACE FUNCTION`` statements are the 0155/0156 bodies with
the schema term removed and nothing else changed. The triggers themselves are
untouched: they reference the functions by name and pick up the replacement
immediately, so no DROP/CREATE TRIGGER is needed.

This only fixes the triggers, so it only affects vectors written from here on.
Rows already in ``activity_tsvectormodel`` keep their polluted vector until the
``rebuild_event_tsvectors`` management command is run as a post-deploy step
(``--tenant_domain <domain>`` for one site, ``--all-tenants`` for every site).
The rebuild is deliberately not a migration: a table-wide walk does not belong
in the deploy path, and keeping it a command lets a site be rebuilt on demand.

Note: ``tsvector_eventnote_trigger`` (0157) never included the schema term and
is deliberately left alone.
"""

from django.db import migrations

# --- Forward: 0155/0156 bodies minus the et.schema term ------------------------

CREATE_TS_VECTOR_DOC_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION tsvector_doc_trigger() RETURNS TRIGGER AS
$$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO activity_tsvectormodel (event_id, tsvector_event, id, das_tenant_id)
        SELECT e.id,
               setweight(to_tsvector(et.display)::tsvector, 'A') ||
               setweight(to_tsvector(coalesce(e.title, '')), 'B') ||
               setweight(to_tsvector((ed.data #>> '{event_details}')::text), 'A'),
               uuid_generate_v4(),
               new.das_tenant_id
        FROM activity_event e
                 JOIN activity_eventtype et ON e.event_type_id = et.id
                 JOIN activity_eventdetails ed ON e.id = ed.event_id
        WHERE ed.id = NEW.id
        ON CONFLICT DO NOTHING;
    ELSIF (TG_OP = 'UPDATE') THEN
        UPDATE activity_tsvectormodel ts
        SET tsvector_event = setweight(to_tsvector(et.display)::TSVECTOR, 'A') ||
                             setweight(to_tsvector(coalesce(e.title, '')), 'B') ||
                             setweight(to_tsvector((ed.data #>> '{event_details}')::TEXT), 'A')
        FROM activity_event e,
             activity_eventtype et,
             activity_eventdetails ed
        WHERE e.event_type_id = et.id
          AND ed.event_id = e.id
          AND e.id = ts.event_id
          AND ed.id = OLD.id
          AND ed.das_tenant_id = OLD.das_tenant_id;
    END IF;
    RETURN new;
END
$$ LANGUAGE plpgsql;
"""

CREATE_TS_VECTOR_EVENT_TITLE_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION tsvector_event_title_trigger() RETURNS trigger as
$$
begin
    update activity_tsvectormodel ts
    set tsvector_event = setweight(to_tsvector(et.display)::tsvector, 'A') ||
                         setweight(to_tsvector(coalesce(e.title, '')), 'B') ||
                         setweight(to_tsvector((ed.data #>> '{event_details}')::text), 'A')
    from activity_event e,
         activity_eventtype et,
         activity_eventdetails ed
    where e.event_type_id = et.id
      and ed.event_id = e.id
      and e.id = ts.event_id
      and e.id = OLD.id
      AND e.das_tenant_id = OLD.das_tenant_id;
    return new;
end
$$ LANGUAGE plpgsql;
"""

# --- Reverse: verbatim 0155/0156 bodies, schema term included -----------------

REVERSE_TS_VECTOR_DOC_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION tsvector_doc_trigger() RETURNS TRIGGER AS
$$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO activity_tsvectormodel (event_id, tsvector_event, id, das_tenant_id)
        SELECT e.id,
               setweight(to_tsvector(et.display)::tsvector, 'A') ||
               setweight(to_tsvector(coalesce(e.title, '')), 'B') ||
               setweight(to_tsvector(et.schema::text), 'B') ||
               setweight(to_tsvector((ed.data #>> '{event_details}')::text), 'A'),
               uuid_generate_v4(),
               new.das_tenant_id
        FROM activity_event e
                 JOIN activity_eventtype et ON e.event_type_id = et.id
                 JOIN activity_eventdetails ed ON e.id = ed.event_id
        WHERE ed.id = NEW.id
        ON CONFLICT DO NOTHING;
    ELSIF (TG_OP = 'UPDATE') THEN
        UPDATE activity_tsvectormodel ts
        SET tsvector_event = setweight(to_tsvector(et.display)::TSVECTOR, 'A') ||
                             setweight(to_tsvector(coalesce(e.title, '')), 'B') ||
                             setweight(to_tsvector(et.schema::TEXT), 'B') ||
                             setweight(to_tsvector((ed.data #>> '{event_details}')::TEXT), 'A')
        FROM activity_event e,
             activity_eventtype et,
             activity_eventdetails ed
        WHERE e.event_type_id = et.id
          AND ed.event_id = e.id
          AND e.id = ts.event_id
          AND ed.id = OLD.id
          AND ed.das_tenant_id = OLD.das_tenant_id;
    END IF;
    RETURN new;
END
$$ LANGUAGE plpgsql;
"""

REVERSE_TS_VECTOR_EVENT_TITLE_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION tsvector_event_title_trigger() RETURNS trigger as
$$
begin
    update activity_tsvectormodel ts
    set tsvector_event = setweight(to_tsvector(et.display)::tsvector, 'A') ||
                         setweight(to_tsvector(coalesce(e.title, '')), 'B') ||
                         setweight(to_tsvector(et.schema::text), 'B') ||
                         setweight(to_tsvector((ed.data #>> '{event_details}')::text), 'A')
    from activity_event e,
         activity_eventtype et,
         activity_eventdetails ed
    where e.event_type_id = et.id
      and ed.event_id = e.id
      and e.id = ts.event_id
      and e.id = OLD.id
      AND e.das_tenant_id = OLD.das_tenant_id;
    return new;
end
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("activity", "0204_alter_eventdetails_options"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_TS_VECTOR_DOC_TRIGGER_FUNCTION,
            reverse_sql=REVERSE_TS_VECTOR_DOC_TRIGGER_FUNCTION,
        ),
        migrations.RunSQL(
            sql=CREATE_TS_VECTOR_EVENT_TITLE_TRIGGER_FUNCTION,
            reverse_sql=REVERSE_TS_VECTOR_EVENT_TITLE_TRIGGER_FUNCTION,
        ),
    ]
