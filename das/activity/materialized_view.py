from activity.models import Event, EventType
from utils import schema_utils

from django.db import connection

cursor = connection.cursor()
table_name = 'event_details_view'


def load_schema():
    render_f = schema_utils.get_schema_renderer_method()
    schema_accumulator = {}

    for et in EventType.objects.all():
        schema_accumulator[et.value] = render_f(et.schema)
    return schema_accumulator


def generate_DDL():
    lines = []
    lines.append(
        f'create materialized view if not exists {table_name} as select ')
    lines.append('ed.event_id, et.display as "event_type", ')

    fieldset = set()
    schema_accumulator = load_schema()
    for a, b in generate_field_details(schema_accumulator):
        path = ','.join(a)
        fielddef = f'(data#>>\'{{{path}}}\')::{b} as "{a[1]}"'
        fieldset.add(fielddef)
    lines.append(',\n'.join(fieldset))
    lines.append(' from activity_eventdetails ed ')
    lines.append(' join activity_event e on e.id = ed.event_id ')
    lines.append(' join activity_eventtype et on et.id = e.event_type_id ')
    # lines.append(' with no data ')

    return lines


def _cursor():
    cursor_wrapper = connection.cursor()
    cursor = cursor_wrapper.cursor
    return cursor


def execute_DDL():
    query_string = ''
    for line in generate_DDL():
        query_string += line
    cursor = _cursor()
    cursor.execute(query_string)


def check_db_view_exists():
    cursor = _cursor()
    cursor.execute("SELECT to_regclass('public.{0}')".format(table_name))
    view_exist = cursor.fetchone()[0]
    return bool(view_exist)


def re_create_view():
    if check_db_view_exists():
        cursor = _cursor()
        cursor.execute(f'DROP MATERIALIZED VIEW {table_name}')
        execute_DDL()
    else:
        execute_DDL()


def refresh_materialized_view():
    if check_db_view_exists():
        cursor = _cursor()
        cursor.execute(f"REFRESH MATERIALIZED VIEW {table_name}")
    else:
        execute_DDL()


def generate_field_details(schema_accumulator):
    used_properties = set()

    for k, v in schema_accumulator.items():
        properties = v['schema']['properties']

        for propkey, propval in properties.items():

            proptype = propval.get('type', '')
            prophash = f'{propkey}:{proptype}'
            if prophash in used_properties:
                continue
            used_properties.add(prophash)

            propkey = f"{propkey}"
            if propval.get('enum'):
                if propval.get('type') == 'string':
                    yield ('ed.event_details', propkey, 'name'), 'TEXT'

            elif propval.get('type') == 'string':
                yield ('ed.event_details', propkey), 'TEXT'

            elif propval.get('type') == 'number':
                yield ('ed.event_details', propkey), 'NUMERIC'
