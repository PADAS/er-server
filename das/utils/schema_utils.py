import html
import json
import jsonschema
import logging
import re

from collections import OrderedDict
from django.apps import apps
from django.template import Template, Context
from django.template.base import VariableNode

from choices.models import Choice, DynamicChoice
from utils.memoize import memoize


logger = logging.getLogger(__name__)


LOOKUP_ATTR = 'lookup'
FIELD_ATTR = 'field'
TYPE_ATTR = 'type'
TAG_ATTR = 'tag'


def get_replacement_fields_in_schema(schema):
    template = Template(schema)

    fields = []
    for node in template.nodelist:
        if type(node) is VariableNode:
            field_tag = node.token.contents
            field_details = field_tag.split('___')
            if len(field_details) != 3:
                raise NameError('Incorrect event render tag: ' + field_tag)

            fields.append({'lookup': field_details[0],
                           'field': field_details[1],
                           'type': field_details[2],
                           'tag': node.token.contents})

    return fields


def get_dynamic_choices(field_details, as_string=True):

    return_val = _get_dynamic_choices(field_details)
    return json.dumps(return_val) if as_string else return_val


def _get_dynamic_choices(field_details):

    dynamic_choice = DynamicChoice.objects.filter(id=field_details['field']).first()

    # Short-circuit if there aren't any DynamicChoices found for this field.
    if dynamic_choice is None:
        return []

    try:
        choice_criteria = json.loads(dynamic_choice.criteria)
    except json.decoder.JSONDecodeError as jde:
        logger.exception('Error decoding criteria for dynamic choice %s. Criteria is: %s', str(dynamic_choice.id),
                         dynamic_choice.criteria)
        return []

    model_to_filter = apps.get_model(dynamic_choice.model_name)

    options = OrderedDict()
    for row in model_to_filter.objects.filter(*choice_criteria).order_by(dynamic_choice.display_col):
        value = getattr(row, dynamic_choice.value_col, None)
        display = getattr(row, dynamic_choice.display_col, None)
        options[str(value)] = str(display)

    if field_details['type'] == 'names':
        return_val = options
    elif field_details['type'] == 'map':
        return_val = list([{'value': k, 'name': v} for k, v in options.items()])
    else:
        return_val = list(options.keys())

    return return_val


def get_enum_choices(field_details, as_string=True):

    options = OrderedDict()
    for choice in Choice.objects.filter(model='activity.event', field=field_details['field']).extra(select={'lower_name': 'lower(display)'}).order_by('ordernum', 'lower_name'):
        options[choice.value] = choice.display

    if field_details['type'] == 'names':
        return_val = options
    elif field_details['type'] == 'map':
        return_val = []
        for k, v in options.items():
            return_val.append({
                'value': k,
                'name': v
            })
    else:
        return_val = list(options.keys())

    if as_string:
        return json.dumps(return_val)

    return return_val


def get_table_choices(field_details, as_string=True):

    options = OrderedDict()
    model = apps.get_model('choices.{0}'.format(field_details['field']))

    for row in model.objects.all().extra(select={'lower_name': 'lower(name)'}).order_by('ordernum', 'lower_name'):
        options[str(row.id)] = str(row.name)

    if field_details['type'] == 'names':
        return_val = options
    elif field_details['type'] == 'map':
        return_val = []
        for k, v in options.items():
            return_val.append({
                'value': k,
                'name': v
            })
    else:
        return_val = list(options.keys())

    if as_string:
        return json.dumps(return_val)

    return return_val


def get_schema_renderer_method():
    @memoize
    def render_f(schema):

        schema_fields = get_replacement_fields_in_schema(schema)

        parameters = {}
        for schema_field in schema_fields:
            if schema_field['lookup'] == 'enum':
                parameters[schema_field['tag']
                           ] = get_enum_choices(schema_field)
            elif schema_field['lookup'] == 'query':
                parameters[schema_field['tag']
                           ] = get_dynamic_choices(schema_field)
            elif schema_field['lookup'] == 'table':
                parameters[schema_field['tag']
                           ] = get_table_choices(schema_field)

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
            schema = get_schema_renderer_method()(event.event_type.schema)

        jsonschema.validate(
            event.event_details.first().data, schema)
        return True
    except:
        if raise_exception:
            raise

    return False


def extract_from_list(values):

    names = []
    ids = []
    for value in values:
        if value and not isinstance(value, dict):
            logger.warning(f'extract_from_list value is not a dict: {value} from {values}')
            return value, value

        if 'name' not in value:
            logger.warning(f'extract_from_list name not in value: {value} from {values}')
            return '', ''

        names.append(value['name'])
        ids.append(value['value'])

    return ';'.join(ids), ';'.join(names)


def extract_from_dict_or_string(schema_item, value):
    # value might be a dict, in which case it includes a 'value' attribute.
    if isinstance(value, dict):
        value = value.get('value') or str(value)

    key = value

    # Get the value and display value for the current value
    if schema_item.get('type', None) == 'string':
        if value in schema_item.get('enumNames', {}):
            value = schema_item['enumNames'][value]

    return key, value


def extractor(schema_item, definition, value):

    if isinstance(value, list):
        key, val = extract_from_list(value)
    else:
        key, val = extract_from_dict_or_string(schema_item, value)

    if 'title' in schema_item:
        return schema_item['title'], val, key
    else:
        for definition_item in definition:
            if isinstance(definition_item, dict):
                if 'key' not in definition_item:
                    logger.warning(f'key not found in definition {definition}')
                    continue
                if 'key' not in schema_item:
                    logger.warning(f'key not found in schema_item {schema_item}')
                    continue
                if definition_item['key'] == schema_item['key']:
                    return definition_item.get('title'), val, key


def generate_index(start_at=0, incr=1):
    while True:
        yield start_at
        start_at = start_at + incr


def definition_keys(form_definition: list, index_values=None):
    '''
    Calculate map of key to order, as indicated in schema.definition.

    It supports fieldsets by recursion.
    '''

    index_values = index_values or generate_index()
    
    for k in form_definition:
        if isinstance(k, str):
            yield (k, next(index_values))

        elif isinstance(k, dict):
            if 'key' in k:
                yield (k['key'], next(index_values))

            elif 'items' in k and isinstance(k['items'], list):
                yield from definition_keys(k['items'], index_values=index_values)


def definition_key_order_as_dict(schema):
    return OrderedDict(definition_keys(schema.get('definition', [])))


def detail_resolver(schema, key, value):
    properties = schema['schema']['properties']
    # It is possible for an event to have saved elements in its details that
    # don't correspond to a current item in its schema. Typically this comes
    # from a change in the event type without re-saving the details.
    schema_item = properties.get(key, None)
    if schema_item:
        return extractor(schema_item, schema.get('definition', []), value)
    else:
        return None


def generate_details(event, schema):
    event_details = event.event_details.first().data.get('event_details', {})

    definition_order = dict(definition_keys(schema.get('definition', [])))

    for k, v in event_details.items():
        resolved_details = detail_resolver(schema, k, v)
        if resolved_details:
            value = resolved_details[1]
            yield {'name': resolved_details[0],
                   'value': html.escape(value) if isinstance(value, str) else value,
                   'order': definition_order.get(k, 99)}


def get_display_values_for_event_details(event_details, schema):
    ret = {}
    for k, v in event_details.items():
        resolved_details = detail_resolver(schema, k, v)

        logger.debug(f'Resolved details for {k} {v} = {resolved_details}')
        if resolved_details:
            title, display, value = resolved_details
            ret.update({
                k: resolved_details[2],
                resolved_details[0]: resolved_details[1]
            })
    return ret


def get_details_and_display_values(event, schema):
    try:
        event_details = event.event_details.first().data.get('event_details', {})
        return get_display_values_for_event_details(event_details, schema)
    except AttributeError:
        return {}


def get_rendered_schema(schema):
    renderer = get_schema_renderer_method()
    rendered_schema = renderer(schema)
    return rendered_schema['schema']


def get_all_fields(schema):
    try:
        template = Template(schema)

        empty_params = {}
        for node in template.nodelist:
            if type(node) is VariableNode:
                empty_params[node.token.contents] = []

        if len(empty_params) > 0:
            rendered_schema = template.render(
                Context(empty_params, autoescape=False))
            schema_json = json.loads(rendered_schema)
        else:
            schema_json = json.loads(schema)

        return schema_json['schema']['properties'].keys()
    except Exception as ex:
        logger.error("Error rendering schema with empty data", ex)
        return []


def get_empty_params(schema):
    template = Template(schema)
    empty_params = {}
    for node in template.nodelist:
        if type(node) is VariableNode:
            empty_params[node.token.contents] = []
    return empty_params


def render_schema_template(schema, parameters):
    rendered_template = schema
    if len(parameters) > 0:
        template = Template(schema)
        rendered_template = template.render(
            Context(parameters, autoescape=False))
    return json.loads(rendered_template, object_pairs_hook=OrderedDict)


def get_replacement_fields_in_schema(schema):
    template = Template(schema)

    fields = []
    for node in template.nodelist:
        if type(node) is VariableNode:
            field_tag = node.token.contents
            field_details = field_tag.split('___')
            if len(field_details) != 3:
                raise NameError('Incorrect event render tag: ' + field_tag)

            fields.append({'lookup': field_details[0],
                           'field': field_details[1],
                           'type': field_details[2],
                           'tag': node.token.contents})

    return fields


def format_key_for_title(key):
    titleStr = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', key)
    titleStr = re.sub('([a-z0-9])([A-Z])', r'\1 \2', titleStr).lower()
    return titleStr.title()


def find_display_value_for_key_in_definition(schema, key):
    for item in schema.get('definition', []):
        if not isinstance(item, dict):
            continue
        if 'key' in item and item['key'] == key and 'title' in item:
            return item['title']
    return None


def get_display_value_header_for_key(schema, key):
    if key in schema['schema']['properties'] and 'title' in schema['schema']['properties'][key]:
        return schema['schema']['properties'][key]['title']
    return find_display_value_for_key_in_definition(schema, key) or format_key_for_title(key)
