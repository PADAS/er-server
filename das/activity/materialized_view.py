import json
from activity.models import EventType
from utils import schema_utils

from django.db import connection

cursor = connection.cursor()
table_name = 'event_details_view'


def load_schema():
    render_f = schema_utils.get_schema_renderer_method()
    schema_accumulator = {}

    for et in EventType.objects.all():
        try:
            schema_accumulator[et.value] = render_f(et.schema)
        except json.decoder.JSONDecodeError as exc:
            raise Exception(f"{exc} in eventtype '{et}'")
    return schema_accumulator


def generate_DDL():
    lines = []
    lines.append(
        f'create materialized view if not exists {table_name} as select ')
    lines.append('ed.event_id, et.display as "event_type", ')

    fieldset = set()
    schema_accumulator = load_schema()
    for json_path, data_type in generate_field_details(schema_accumulator):
        fielddef = query_statement(json_path, data_type)
        fieldset.add(fielddef)
    lines.append(',\n'.join(fieldset))
    lines.append(' from activity_eventdetails ed ')
    lines.append(' join activity_event e on e.id = ed.event_id ')
    lines.append(' join activity_eventtype et on et.id = e.event_type_id ')
    # lines.append(' with no data ')

    return lines


def query_statement(json_path, data_type):
    array_path = ','.join([json_path[0], json_path[1]])
    path = ','.join(json_path)

    if data_type == 'TEXT[]':
        array_elements = f"select jsonb_array_elements(data#>'{{{array_path}}}')"
        query_string = f"case when jsonb_typeof(data#> '{{{array_path}}}') = 'array' then case\
            when array_position(array({array_elements}->>'value'), null) is not null\
                then array({array_elements})::text[] else array({array_elements}->>'value') end end as {json_path[1]}"
    elif data_type == 'NUMERIC':
        # Wrap in a function that'll safely coerce values to NUMERIC.
        query_string = f'TO_NUMERIC((data#>>\'{{{path}}}\')::TEXT) as "{json_path[1]}"'
    else:
        removed_value = ','.join(json_path[:-1])  # value removed
        query_string = f'case when data#>>\'{{{path}}}\' IS NOT NULL THEN (data#>>\'{{{path}}}\')::{data_type}\
            else (data#>>\'{{{removed_value}}}\')::{data_type} end as "{json_path[1]}"'
    return query_string


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
        cursor.execute(f'DROP MATERIALIZED VIEW IF EXISTS {table_name}')
    execute_DDL()


def refresh_materialized_view():
    if check_db_view_exists():
        cursor = _cursor()
        cursor.execute(f"REFRESH MATERIALIZED VIEW {table_name}")
    else:
        execute_DDL()


def generate_field_details(schema_accumulator):
    used_properties = set()

    for v in schema_accumulator.values():
        properties = v['schema']['properties']

        for prop_key, prop_val in properties.items():

            if prop_key in used_properties:
                continue
            used_properties.add(prop_key)
            if prop_val.get('type') == 'string':
                yield ('event_details', prop_key, 'value'), 'TEXT'

            elif prop_val.get('type') == 'number':
                yield ('event_details', prop_key), 'NUMERIC'

            # elif bool({'checkboxes', 'array'} & set(prop_val.values())):
            elif prop_val.get('type') == 'array' or prop_val.get('type') == "checkboxes":
                yield ('event_details', prop_key), 'TEXT[]'
