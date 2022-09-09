import copy
import html
import json
import logging
import re
import typing
import uuid
from collections import OrderedDict

import jsonschema

from django.apps import apps
from django.template import Context, Template
from django.template.base import TextNode, VariableNode

from activity.exceptions import (SCHEMA_ERROR_MISSING_DOLLAR_SIGN_SCHEMA,
                                 SchemaValidationError, UnmappableFormKeyError)
from activity.models import EventDetails
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
                raise NameError(f'Invalid schema tag: {repr(field_tag)}')

            fields.append({'lookup': field_details[0],
                           'field': field_details[1],
                           'type': field_details[2],
                           'tag': node.token.contents})

    return fields


def get_dynamic_choices(field_details, as_string=True, event=None):

    return_val = _get_dynamic_choices(field_details, event)
    return json.dumps(return_val) if as_string else return_val


def _get_dynamic_choices(field_details, event=None):

    dynamic_choice = DynamicChoice.objects.filter(
        id=field_details['field']).first()

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
    choices = model_to_filter.objects.filter(
        *choice_criteria).order_by(dynamic_choice.display_col)
    if dynamic_choice.model_name == "observations.subject":
        choices = choices.filter(is_active=True)

        event_details = EventDetails.objects.filter(event__id=event)
        if event_details:
            event_detail = event_details.first()
            object_id = event_detail.data.get("event_details").get(
                field_details.get("event_detail"))
            extra_objects = model_to_filter.objects.filter(id=object_id)
            choices = choices | extra_objects

    for row in choices:
        value = getattr(row, dynamic_choice.value_col, None)
        display = getattr(row, dynamic_choice.display_col, None)
        options[str(value)] = str(display)

    if field_details['type'] == 'names':
        return_val = options
    elif field_details['type'] == 'map':
        return_val = list([{'value': k, 'name': v}
                           for k, v in options.items()])
    else:
        return_val = list(options.keys())

    return return_val


def get_enum_choices(field_details, as_string=True, queryset=None):
    options = OrderedDict()
    qs = queryset or Choice.objects.all()
    for choice in qs.filter(model='activity.event',
                            field=field_details['field']).extra(
        select={'lower_name': 'lower(display)'}).order_by('ordernum',
                                                          'lower_name'):
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


def get_enumImage_values(field_details, queryset=None):
    qs = queryset or Choice.objects.all()
    options = OrderedDict()
    for choice in qs.filter(model='activity.event', field=field_details['field']).extra(select={'lower_name': 'lower(display)'}).order_by('ordernum', 'lower_name'):
        options[choice.value] = choice.icon

    return {k: v for k, v in options.items() if v}


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
    def memo_enum_choices(enum_choices_identifier):
        field_name, field_type = enum_choices_identifier.split(':')
        return get_enum_choices({'field': field_name, 'type': field_type})

    @memoize
    def memo_dynamic_choices(dynamic_choices_identifier):
        field_name, field_type = dynamic_choices_identifier.split(':')
        return get_dynamic_choices({'field': field_name, 'type': field_type})

    @memoize
    def memo_table_choices(table_choices_identifier):
        field_name, field_type = table_choices_identifier.split(':')
        return get_table_choices({'field': field_name, 'type': field_type})

    @memoize
    def render_f(schema):

        schema_fields = get_replacement_fields_in_schema(schema)

        parameters = {}
        for schema_field in schema_fields:
            if schema_field['lookup'] == 'enum':
                parameters[schema_field['tag']
                           ] = memo_enum_choices('{field}:{type}'.format(**schema_field))
            elif schema_field['lookup'] == 'query':
                parameters[schema_field['tag']
                           ] = memo_dynamic_choices('{field}:{type}'.format(**schema_field))
            elif schema_field['lookup'] == 'table':
                parameters[schema_field['tag']
                           ] = memo_table_choices('{field}:{type}'.format(**schema_field))
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


def extract_from_list(items: list = list, schema_item=None):
    '''
    return a 2-tuple of strings where the first holds IDs and the second holds
    corresponding human-friendly names.
    :param items: a list (of dicts of the format {'name': '', 'value': ''}
    :param schema_item: (default to None)  dictionary contains enumValues, enumNames example:
                        {
                        "key":"carcassrep_species",
                       "type":"array",
                       "title":"Species",
                       "items":{
                          "type":"string",
                          "enumValues":[
                             "bongo",
                             "buffalo"
                          ],
                          "enumNames":{
                             "bongo":"Bongo",
                             "buffalo":"Buffalo"
                          }
                       }
                    }
    :return: 2-tuple (str, str)
    '''
    names = []
    ids = []
    for item in items:
        if item and isinstance(item, (str, bool, int, float)):
            logger.warning(
                f'extract_from_list value is not a dict: {item} from {items}')
            name = item
            if schema_item and isinstance(item, str):
                name = schema_item.get('items', {}).get(
                    'enumNames', {}).get(item, item)

            names.append(str(name))
            ids.append(item)
        elif isinstance(item, dict) and 'name' in item and 'value' in item:
            logger.debug(f'extracting name/value from {item}')
            names.append(item['name'])
            ids.append(item['value'])
        else:
            logger.warning(
                f'extract_from_list cannot parse in value: {item} from {items}')

    return ';'.join(ids), ';'.join(names)


def extract_from_dict_or_string(schema_item, value):
    # value might be a dict, in which case it includes a 'value' attribute.
    display = value
    if isinstance(value, dict):
        display = value.get('name')
        value = value.get('value') or str(value)

    # Get the value and display value for the current value
    if schema_item.get('type', None) == 'string':
        if value in schema_item.get('enumNames', {}):
            display = schema_item['enumNames'][value]
    return value, display


def is_uuid(record):
    try:
        uuid.UUID(str(record))
        return True
    except ValueError:
        return False


def extract_from_definition(schema_item, definition, key, eventdetail_value, extracted_value, display):
    for definition_item in flatten_definition_items(definition):
        if isinstance(definition_item, dict) \
                and (schema_item.get('key') == definition_item.get('key') or key == definition_item.get('key')):
            if definition_item.get("type") == "checkboxes":
                extracted_value, display = handle_checkboxes_in_fieldsets(
                    definition_item, eventdetail_value)
            return definition_item.get('title'), extracted_value, display
    title = schema_item.get('title') or key
    return title, extracted_value, display


def extractor(schema_item, definition, key, eventdetail_value):

    # Determine how the value should appear.
    if isinstance(eventdetail_value, list):
        extracted_value, display = extract_from_list(
            eventdetail_value, schema_item)
    else:
        extracted_value, display = extract_from_dict_or_string(
            schema_item, eventdetail_value)

    # The simplest case is when the json schema specifies the title.
    if 'title' in schema_item:
        if extracted_value == display and all(is_uuid(data) for data in str(display).split(';')):
            return extract_from_definition(
                schema_item, definition, key, eventdetail_value, extracted_value, display)
        return schema_item['title'], extracted_value, display

    if 'key' not in schema_item:
        logger.warning(f'key not found in schema_item {schema_item}')
        return key, extracted_value, display

    return extract_from_definition(
        schema_item, definition, key, eventdetail_value, extracted_value, display)


def handle_checkboxes_in_fieldsets(definition_item, values):
    names = []
    ids = []
    for map_item in definition_item.get("titleMap", []):
        val = map_item["value"]
        is_list_of_dicts = all([isinstance(i, dict) for i in values])
        if is_list_of_dicts:
            return extract_from_list(values)

        if isinstance(values, list) and val in values:
            ids.append(map_item["value"])
            names.append(map_item["name"])
    return ";".join(ids), ";".join(names)


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


def flatten_definition_items(definition: list = list):
    '''
    From a definition list, generate an individual 'item' regardless of whether it's part of a fieldset.
    :param definition: EventType.schema->definition list = []
    :return: generator of 'items'
    '''
    for elem in definition:
        if isinstance(elem, str):
            yield elem

        if isinstance(elem, dict):
            if elem.get('type', None) == 'fieldset' \
                    and 'items' in elem:
                yield from flatten_definition_items(elem['items'])
            else:
                yield elem


def filter_schema_definition(schema: dict, definition_format: str):
    """Change the definition format depending on the type

    Args:
        schema ([dict]): the event type schema, already expanding into a dictionary
        definition_format ([str]): presentation format, [standard, flat]. Flat calls for no fieldsets.
    """
    if definition_format in [None, 'standard']:
        return schema
    elif definition_format == 'flat':
        schema = copy.deepcopy(schema)
        if 'definition' in schema:
            schema['definition'] = list(
                flatten_definition_items(schema['definition']))
        return schema
    raise ValueError(
        f"Unsupported definition presentation type: {definition_format}")


def definition_key_order_as_dict(schema):
    return OrderedDict(definition_keys(schema.get('definition', [])))


def property_keys_order_as_dict(schema):
    properties = schema.get("schema", {}).get("properties", [])
    if properties:
        property_keys = properties.keys()
        return OrderedDict(definition_keys(property_keys))
    return OrderedDict()


def detail_resolver(schema, key, value):
    if key in schema['schema']['properties']:
        schema_item = schema['schema']['properties'][key]
        return extractor(schema_item, schema.get('definition', []), key, value)


def generate_details(event, schema):

    event_details = event.event_details.first()
    if not event_details:
        logger.warning(f'Event No. {event.serial_number} has no event_details')
        return

    if not event_details.data:
        logger.warning(
            f'Event No. {event.serial_number} has no value for event_details.data')
        return

    event_details = event_details.data.get('event_details', {})

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
            title, value, display = resolved_details
            ret.update({
                k: value,
                title: display
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
        return get_rendered_schema(schema)['properties'].keys()
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


def format_key_for_title(key):
    titleStr = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', key)
    titleStr = re.sub('([a-z0-9])([A-Z])', r'\1 \2', titleStr).lower()
    return titleStr.title()


def find_display_value_for_key_in_definition(schema, key):
    for schema_item in schema.get('definition', []):
        if not isinstance(schema_item, dict):
            continue
        if 'key' in schema_item and schema_item['key'] == key and 'title' in schema_item:
            return schema_item['title']
        # fieldsets
        """
        OrderedDict([('type', 'fieldset'), ('htmlClass', 'col-lg-6'), 
        ('items', [OrderedDict([('key', 'reportinternal'), 
        ('type', 'checkboxes'), ('title', 'FieldSet Checkbox Enum'), 
        ('titleMap', [OrderedDict([('value', 'team01'), ('name', 'Team 1')]), 
        OrderedDict([('value', 'team02'), ('name', 'Teams 2')])])])])])
        """
        if 'items' in schema_item and len(schema_item['items']) > 0:
            for item in schema_item.get("items", []):
                if isinstance(item, dict) and 'key' in item and item['key'] == key and 'title' in item:
                    return item['title']
    return None


def get_column_header_name(schema, key):
    '''
    Prefer the title from:
    1. the form definition
    2. The schema properties extra title attribute
    3. A sanitized derivative of the key itself

    :param schema: An EventType.schema  as a dict
    :param key: The document property key
    :return: A title
    '''
    definition_header = find_display_value_for_key_in_definition(schema, key)

    if definition_header:
        return definition_header
    else:
        properties = schema['schema']['properties']
        if key in properties and 'title' in properties[key]:
            return properties[key]['title']

    return format_key_for_title(key)


def get_display_value_header_for_key(schema, key):
    '''
    If the title from the form definition is not the same as the
    title from the schema properties, use the schema properties
    title.
    :param schema: An EventType.schema  as a dict
    :param key: The document property key
    :return: A title
    '''
    definition_header = find_display_value_for_key_in_definition(schema, key)
    properties_title = ""
    properties = schema['schema']['properties']
    if key in properties and 'title' in properties[key]:
        properties_title = properties[key]['title']
    if properties_title and definition_header != properties_title:
        return properties_title
    elif definition_header:
        return definition_header
    else:
        # return property key for fields with no key or title
        return key


def generate_schema_from_document(doc):
    '''
    Generate a JSON schema from the given document.
    :param doc:
    :return: A valid json schema
    '''
    def new_schema_property(k, v):
        title = ' '.join(k.split('_')).title()
        propertytype = 'number' if isinstance(v, (int, float)) else 'string'
        return k, {'type': propertytype, 'title': title}

    schema_properties = dict(new_schema_property(k, v) for k, v in doc.items())

    schema_def = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Auto-generated schema, from incoming data.",
        "type": "object",
        'properties': schema_properties
    }
    return schema_def


def generate_form_definition_from_doc(doc):
    return sorted(doc.keys())


def generate_event_type_schema_from_doc(doc):
    '''
    This function can be used to create a generic EventType.schema that's fitted to the given doc.

    Our EventType.schema attribute is meant to contain a document that includes a 'schema' and a 'definition'.
    The schema is a json schema (or a template that generates a valid json schema).
    The definition attribute is a list of attributes that may include rendering directives.

    :param doc:
    :return:
    '''
    schema = generate_schema_from_document(doc)
    form_def = generate_form_definition_from_doc(doc)

    return {'schema': schema, 'definition': form_def}


def should_auto_generate(schema_string):

    try:
        schema_doc = json.loads(schema_string)
    except json.JSONDecodeError:
        pass
    else:
        if schema_doc.get('auto-generate', False):
            return True
    return False


def validate_eventtype_schema_is_wellformed(schema):
    rendered_schema = get_schema_renderer_method()(schema)
    return validate_rendered_schema_is_wellformed(rendered_schema)


def validate_rendered_schema_is_wellformed(rendered_schema: dict):

    if "$schema" not in rendered_schema.get('schema', {}):
        raise SchemaValidationError(SCHEMA_ERROR_MISSING_DOLLAR_SIGN_SCHEMA)

    properties = rendered_schema['schema'].get('properties')

    if not properties:
        raise SchemaValidationError(
            f'Schema must include a "properties" attribute.')

    # Raise an error if any property exists without essential attributes.
    incomplete_properties_keyset = set()
    property_keyset_1 = {'type', 'title'}
    property_keyset_2 = {'key'}

    for property_key, val in properties.items():
        if all([k in val for k in property_keyset_1]) or all([k in val for k in property_keyset_2]):
            continue
        incomplete_properties_keyset.add(property_key)

    if len(incomplete_properties_keyset) > 0:
        raise SchemaValidationError(
            f'Schema properties {repr(incomplete_properties_keyset)} must include either {repr(property_keyset_1)} or {repr(property_keyset_2)}.')

    # Inspect the form-definition and raise an error if any elements are
    # missing essential elements.
    definition = rendered_schema.get('definition', [])

    definition_keyset = set([x for x, y in definition_keys(definition)])

    schema_keyset = set(properties.keys())

    # Ignore blank or None keys in form definition.
    extra_keys_in_definition = definition_keyset - schema_keyset - {'', None}
    if len(extra_keys_in_definition) > 0:
        raise UnmappableFormKeyError(
            f'Form definition keys {repr(extra_keys_in_definition)} are not present in the schema definition')


def get_values_titlemap(schema):
    # Map VariableNode to TextNode.
    values = []
    template = Template(schema)
    _ = dict(zip(template.nodelist.get_nodes_by_type(VariableNode),
             template.nodelist.get_nodes_by_type(TextNode)))
    for k, v in _.items():
        if 'titleMap' in v.token.contents:
            field_tag = k.token.contents
            field_details = field_tag.split('___')
            values.append(field_details[1])
    return values


def _schema_properties(rendered_schema):
    """walk the schema from top to bottom and depth first, returning only the single item properties.
    For example, during the introspection, unpack arrays and other grouping constructs.

    Args:
        rendered_schema ([type]): the json schema, already rendered with enum, enumNames
    Returns:
        tuple: Return the property name and it's dict of properties as a tuple
    """
    def inner_schema_properties(props):
        for key, value in props.items():
            if value.get("type") == "array" and isinstance(value.get("items"), dict) and value["items"].get("properties"):
                yield from inner_schema_properties(value["items"]["properties"])
            else:
                yield key, value

    for prop_name, props in inner_schema_properties(rendered_schema['schema']['properties']):
        yield prop_name, props


class SchemaChoiceProperty(typing.NamedTuple):
    name: str
    properties: dict
    field_name: str
    lookup: str


def schema_property_choices(schema, rendered_schema):
    """[summary]

    Args:
        schema (str): raw unrendered schema, the template
        rendered_schema (dict): the rendered schema

    Returns:
        list: list of SchemaChoiceProperty found in a schema
    """

    def template_values(schema):
        template = Template(schema)
        for node in template.nodelist:
            if type(node) is VariableNode:
                field_tag = node.token.contents
                field_details = field_tag.split('___')

                if field_details[2] == 'values':
                    yield field_details[1], field_details[0]

    iter_values = template_values(schema)
    for prop_name, props in _schema_properties(rendered_schema):
        if bool({'enum', 'query', 'table'} & props.keys()):
            try:
                field_name, lookup = next(iter_values)
            except StopIteration:
                return
            yield SchemaChoiceProperty(prop_name, props, field_name, lookup)
