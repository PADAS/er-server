from utils import schema_utils
from business_rules import actions, engine, fields, operators, variables, export_rule_data
from activity.models import EventType
from typing import NamedTuple, Callable

import logging

logger = logging.getLogger(__name__)

class EventVariables(variables.BaseVariables):

    def __init__(self, event):
        self.event = event

    @variables.numeric_rule_variable
    def priority(self):
        return self.event.priority

    @variables.string_rule_variable
    def state(self):
        return self.event.state

    # @variables.select_rule_variable(options=EventType.objects.all())


class EventActions(actions.BaseActions):

    def __init__(self, event):
        self.event = event

    @actions.rule_action(params={"recipient": fields.FIELD_TEXT})
    def send_alert(self, recipient):
        print(f'Sending alert for event {self.event} to recipient {recipient}.')


class SchemaAttribute(NamedTuple):
    key: str
    func: Callable
    title: str
    options: list


def create_new_func(key, return_type, label=None, optionslist=None):
    '''
    Create a wrapped function for the given key and return-type.
    :param key: This identifies the key for the Event.details value. It is also used as the function's attribute name.
    :param return_type: The function's return-type -- it determines which business-rules decorator to use.
    :param label: The human friendly name for this variable.
    :param optionslist: None or a list of `{name: n, label: l}` dicts, derived from enumNames if available.
    :return: A getter function that's decorated with an appropriate business-rules @variables decorator.
    '''
    label = label or key.replace('_', ' ').title()
    def f(self):
        return self.event.details.get(key)

    if return_type == 'select':
        return variables.select_rule_variable(label, options=optionslist)(f)
    if return_type == str:
        return variables.string_rule_variable(label)(f)
    elif return_type in (int, float):
        return variables.numeric_rule_variable(label)(f)
    else:
        raise NotImplementedError('I do not support that type yet.')


def translate_schema_type_to_type(option):

    if 'enumNames' in option:
        return 'select'

    if 'type' not in option:
        logger.warning('No \'type\' present in option, so using str. option=%s', option)
        return str

    if option['type'] == 'string':
        return str

    elif option['type'] == 'number':
        return int

    else:
        raise NotImplementedError(f'I don\'t support type \'{option["type"]}\' yet.')


def genoptions(schema_option):
    '''
    Transform an Event-Type choice list from `enumNames` to business-rules friendly list.
    :param schema_option:
    :return:
    '''
    if 'enumNames' in schema_option:
        return [{'name': k, 'label': v} for k, v in schema_option['enumNames'].items()]
    return []


def generate_eventvariables_class(event_type):
    '''
    From an EvenType, generate an EventVariables class adhering to Venmo business rules interface.
    :param event_type: A DAS EventType object that has a valid schema.
    :return: A `Variables` type to be used with Venmo business-rules package.
    '''


    # Render the EventType's schema.
    rendered_schema = schema_utils.get_rendered_schema(event_type.schema)

    # Create an attributes list derived from schema and suitable for creating a Variables class.
    attributeslist = [
        (k, translate_schema_type_to_type(v), v.get('title', k), genoptions(v))
        for k, v in rendered_schema['properties'].items()
    ]
    attrs = dict( (attr, create_new_func(attr, attrtype, label=label, optionslist=optionslist))
                  for attr, attrtype, label, optionslist in attributeslist)

    # Invent a class name based on the EventType's display value.
    classname = event_type.display.replace(' ', '')

    return type(classname, (EventVariables,), attrs)


def generate_global_event_variables(event_types):
    '''
    From a list of EventTypes, generate an EventVariables class adhering to Venmo business rules interface.
    :param event_type: A DAS EventType object that has a valid schema.
    :return: A `Variables` type to be used with Venmo business-rules package.
    '''

    attributes_accumulator = {}
    # Render the EventType's schema.
    for event_type in event_types:
        rendered_schema = schema_utils.get_rendered_schema(event_type.schema)

        # Create an attributes list derived from schema and suitable for creating a Variables class.
        for k, v in rendered_schema['properties'].items():
            attributes_accumulator.setdefault(k, (k, translate_schema_type_to_type(v), v.get('title', k), genoptions(v)))

    attrs = dict( (attr, create_new_func(attr, attrtype, label=label, optionslist=optionslist))
                  for attr, attrtype, label, optionslist in attributes_accumulator.values())

    # Invent a class name.
    classname = 'GlobalEventVariables'
    return type(classname, (EventVariables,), attrs)


def render_global_eventvariables(event_types):

    variables_class = generate_global_event_variables(event_types)

    return export_rule_data(variables_class, EventActions)



