
from choices.models import Choice, DynamicChoice
from django.apps import apps
from django.template import Template
from django.template.base import VariableNode
from utils.json import loads, dumps


def get_fields_in_schema(schema):
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
    dynamic_choice = DynamicChoice.objects.filter(id=field_details['field']).first()

    model_to_filter = apps.get_model(dynamic_choice.model_name)

    options = {}
    for row in model_to_filter.objects.filter(loads(dynamic_choice.criteria)):
        value = getattr(row, dynamic_choice.value_col, None)
        display = getattr(row, dynamic_choice.display_col, None)
        options[str(value)] = str(display)


    if field_details['type'] == 'names':
        return_val = options
    else:
        return_val = list(options.keys())

    if as_string:
        return dumps(return_val)

    return return_val


def get_enum_choices(field_details, as_string=True):

    options = {}
    for choice in Choice.objects.filter(model='activity.event', field=field_details['field']):
        options[choice.value] = choice.display

    if field_details['type'] == 'names':
        return_val = options
    else:
        return_val = list(options.keys())

    if as_string:
        return dumps(return_val)

    return return_val


def get_table_choices(field_details, as_string=True):

    options = {}
    model = apps.get_model('choices.{0}'.format(field_details['field']))

    for row in model.objects.all():
        options[str(row.id)] = str(row.name)

    if field_details['type'] == 'names':
        return_val = options
    else:
        return_val = list(options.keys())

    if as_string:
        return dumps(return_val)

    return return_val
