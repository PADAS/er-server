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


logger = logging.getLogger(__name__)

LOOKUP_ATTR = 'lookup'
FIELD_ATTR = 'field'
TYPE_ATTR = 'type'
TAG_ATTR = 'tag'


class SchemaUtils():

    def get_replacement_fields_in_schema(self, schema):
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

    def get_dynamic_choices(self, field_details, as_string=True):
        dynamic_choice = DynamicChoice.objects.filter(
            id=field_details['field']).first()
        model_to_filter = apps.get_model(dynamic_choice.model_name)

        options = OrderedDict()
        for row in model_to_filter.objects.filter(*json.loads(dynamic_choice.criteria)).order_by(dynamic_choice.display_col):
            value = getattr(row, dynamic_choice.value_col, None)
            display = getattr(row, dynamic_choice.display_col, None)
            options[str(value)] = str(display)

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

    def get_enum_choices(self, field_details, as_string=True):

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

    def get_table_choices(self, field_details, as_string=True):

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

    def memoize(self, f):
        '''
        Memoize for single-argument function F(hashable)
        '''

        class memoize(dict):
            def __missing__(self, key):
                ret = self[key] = f(key)
                return ret

        return memoize().__getitem__

    def schema_renderer(self):
        @self.memoize
        def render_f(schema):

            schema_fields = self.get_replacement_fields_in_schema(schema)

            parameters = {}
            for schema_field in schema_fields:
                if schema_field['lookup'] == 'enum':
                    parameters[schema_field['tag']
                               ] = self.get_enum_choices(schema_field)
                elif schema_field['lookup'] == 'query':
                    parameters[schema_field['tag']
                               ] = self.get_dynamic_choices(schema_field)
                elif schema_field['lookup'] == 'table':
                    parameters[schema_field['tag']
                               ] = self.get_table_choices(schema_field)

            if parameters:
                template = Template(schema)
                rendered_template = template.render(
                    Context(parameters, autoescape=False))
            else:
                rendered_template = schema

            return json.loads(rendered_template, object_pairs_hook=OrderedDict)

        return render_f

    def validate(self, event, schema=None, raise_exception=False):
        '''
        Validate event details against a rendered_schema.
        '''
        try:
            if not schema:
                schema = self.schema_renderer()(event.event_type.schema)

            result = jsonschema.validate(
                event.event_details.first().data, schema)
            return True
        except Exception as ex:
            if raise_exception:
                raise

        return False

    def extractor(self, schema_item, value):
        key = value
        # value might be a dict, in which case it includes a 'value' attribute.
        if isinstance(value, dict):
            value = value.get('value') or str(value)

        if schema_item.get('type', None) == 'string':
            if 'enumNames' in schema_item:
                if value in schema_item['enumNames']:
                    value = schema_item['enumNames'][value]
        return (schema_item['title'], value, key)

    def definition_key_order(self, schema):
        '''
        Calculate map of key to order, as indicated in schema.definition.
        '''
        for i, k in enumerate(schema.get('definition', [])):
            if isinstance(k, str):
                yield (k, i)
            elif isinstance(k, dict) and 'key' in k:
                yield (k['key'], i)

    def definition_key_order_as_dict(self, schema):
        '''
        Calculate map of key to order, as indicated in schema.definition.
        '''
        ret = OrderedDict()
        for i, k in enumerate(schema.get('definition', [])):
            if isinstance(k, str):
                ret[k] = i
            elif isinstance(k, dict) and 'key' in k:
                ret[k['key']] = i
        return ret

    def generate_details(self, event, schema):
        event_details = event.event_details.first().data.get('event_details', {})

        def resolver(schema, key, value):
            properties = schema['schema']['properties']
            schema_item = properties[key]
            return self.extractor(schema_item, value)

        definition_order = dict(self.definition_key_order(schema))

        for k, v in event_details.items():
            name, value, key = resolver(schema, k, v)
            yield {'name': name,
                   'value': html.escape(value) if isinstance(value, str) else value,
                   'order': definition_order.get(k, 99)
                   }

    def generate_details_with_display_values(self, event, schema):
        event_details = event.event_details.first().data.get('event_details', {})

        def resolver(schema, key, value):
            properties = schema['schema']['properties']
            schema_item = properties[key]
            extracted_values = self.extractor(schema_item, value)
            return {key:  extracted_values[2],
                    extracted_values[0]: extracted_values[1]}

        definition_order = dict(self.definition_key_order(schema))

        ret = {}
        for k, v in event_details.items():
            ret.update(resolver(schema, k, v))
        return ret

    def get_rendered_schema(self, schema):
        renderer = self.schema_renderer()
        rendered_schema = renderer(schema)
        return rendered_schema['schema']

    def get_all_fields(self, schema):
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

    def get_empty_params(self, schema):
        template = Template(schema)
        empty_params = {}
        for node in template.nodelist:
            if type(node) is VariableNode:
                empty_params[node.token.contents] = []
        return empty_params

    def render_schema_template(self, schema, parameters):
        rendered_template = schema
        if len(parameters) > 0:
            template = Template(schema)
            rendered_template = template.render(
                Context(parameters, autoescape=False))
        return json.loads(rendered_template, object_pairs_hook=OrderedDict)

    def get_replacement_fields_in_schema(self, schema):
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

    def get_all_fields(self, schema):
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

    def format_key_for_title(self, key):
        titleStr = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', key)
        titleStr = re.sub('([a-z0-9])([A-Z])', r'\1 \2', titleStr).lower()
        return titleStr.title()

    def find_display_value_for_key_in_definition(self, schema, key):
        for item in schema['definition']:
            if not isinstance(item, dict):
                continue
            if 'key' in item and item['key'] == key and 'title' in item:
                return item['title']
        return None

    def get_display_value_header_for_key(self, schema, key):
        if 'title' in schema['schema']['properties'][key]:
            return schema['schema']['properties'][key]['title']
        return self.find_display_value_for_key_in_definition(schema, key) or self.format_key_for_title(key)
