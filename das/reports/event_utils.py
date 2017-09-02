from activity import schema_utils
from django.template import Template, Context
import json
from collections import OrderedDict
import jsonschema
import html


def memoize(f):
    '''
    Memoize for single-argument function F(hashable)
    '''

    class memoize(dict):
        def __missing__(self, key):
            ret = self[key] = f(key)
            return ret

    return memoize().__getitem__


def schema_renderer():
    @memoize
    def render_f(schema):

        schema_fields = schema_utils.get_replacement_fields_in_schema(schema)

        parameters = {}
        for schema_field in schema_fields:
            if schema_field['lookup'] == 'enum':
                parameters[schema_field['tag']
                           ] = schema_utils.get_enum_choices(schema_field)
            elif schema_field['lookup'] == 'query':
                parameters[schema_field['tag']
                           ] = schema_utils.get_dynamic_choices(schema_field)
            elif schema_field['lookup'] == 'table':
                parameters[schema_field['tag']
                           ] = schema_utils.get_table_choices(schema_field)

        if parameters:
            template = Template(schema)
            rendered_template = template.render(
                Context(parameters, autoescape=False))
        else:
            rendered_template = schema

        return json.loads(rendered_template, object_pairs_hook=OrderedDict)

    return render_f


def validate(event, schema=None, raise_exception=False):
    '''
    Validate event details against a rendered_schema.
    '''
    try:
        if not schema:
            schema = schema_renderer()(event.event_type.schema)

        jsonschema.validate(event.event_details.first().data, schema)
        True
    except:
        if raise_exception:
            raise
        return False


def extractor(schema_item, value):
    # value might be a dict, in which case it includes a 'value' attribute.
    if isinstance(value, dict):
        value = value.get('value') or str(value)

    if schema_item['type'] == 'string':
        if 'enumNames' in schema_item:
            if value in schema_item['enumNames']:
                value = schema_item['enumNames'][value]
    return (schema_item['title'], value)


def definition_key_order(schema):
    '''
    Calculate map of key to order, as indicated in schema.definition.
    '''
    for i, k in enumerate(schema.get('definition', [])):
        if isinstance(k, str):
            yield (k, i)
        elif isinstance(k, dict) and 'key' in k:
            yield (k['key'], i)


def generate_details(event, schema):
    event_details = event.event_details.first().data.get('event_details', {})

    def resolver(schema, key, value):
        properties = schema['schema']['properties']
        schema_item = properties[key]
        return extractor(schema_item, value)

    definition_order = dict(definition_key_order(schema))

    for k, v in event_details.items():
        name, value = resolver(schema, k, v)
        yield {'name': name,
               'value': html.escape(value) if isinstance(value, str) else value,
               'order': definition_order.get(k, 99)
               }
