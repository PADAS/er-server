from utils import schema_utils
import json
from business_rules import actions, engine, fields, operators, variables, export_rule_data

from django.utils.dateparse import parse_duration

from datetime import datetime, timedelta
import pytz

from typing import NamedTuple, Callable, Dict, Any

import logging

from activity.models import EventType, Event

# Use string value of priority as value (ex. '0') to satisfy rules engine.
priority_options = [dict(name=str(x), label=y) for x, y in Event.PRIORITY_CHOICES]

state_options = [dict(name=x, label=y) for x, y in Event.STATE_CHOICES]

state_change_options = [
    {
        'name': 'new',
        'label': 'New',
    },
    {
        'name': 'updated',
        'label': 'Updated',
    },
    {
        'name': 'resolved',
        'label': 'Resolved',
    },
]

logger = logging.getLogger(__name__)


class EventVariables(variables.BaseVariables):

    def __init__(self, event):
        self.event = event

    @variables.select_multiple_rule_variable(label='Priority', options=priority_options)
    def priority(self):
        return [str(self.event.priority),]

    @variables.select_multiple_rule_variable(label='State', options=state_options)
    def state(self):
        return [self.event.state,]

    @variables.select_multiple_rule_variable(label='State Change', options=state_change_options)
    def state_change(self):
        return [getattr(self.event, 'state_change', None),]


class EventActions(actions.BaseActions):

    def __init__(self, event):
        self.event = event

    @actions.rule_action(params={"recipient": fields.FIELD_TEXT,})
    def send_alert(self, recipient):
        print(f'Sending alert for event {self.event} to recipient {recipient}.')


class SchemaAttribute(NamedTuple):
    key: str
    return_type: Any
    title: str
    options: list


class Schedule:
    '''
    A Schedule is defined by a dictionary whereby each property is the name of a day of the week. Each value is a
    list of tuples where each tuple indicates a range of time of the form ('hh:mm', 'hh:mm').
    An example range is: ('08:30', '14:00') to represent a range from 8:30am to 2:00pm.

    A complete example is:

        {
            "monday": [("08:00", "12:00"), ("13:00", "17:30")],
            "wednesday": [("08:00", "12:00"), ("13:00", "17:30")]
        }

    Once initialized you can ask if a datetime is in the Schedule.
    '''
    days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    # reverse_dow: Dict[int, str] = dict((i, name) for i, name in enumerate(days_of_week, start=1))

    def __init__(self, periods: Dict[str, list]):
        self.periods = periods

    def __contains__(self, value):

        # Truncate the timestamp to our finest granularity.
        value = value.replace(second=0, microsecond=0)

        relevant_periods = self.periods.get(self.days_of_week[value.isoweekday()-1])
        if relevant_periods:
            return self.test_timestamp(value, relevant_periods)
        return False

    def __repr__(self):
        return json.dumps(self.periods)

    def test_timestamp(self, sample_ts, periods):

        if not isinstance(sample_ts, datetime):
            return ValueError(f'Type {type(sample_ts)} is not supported.')

        # Calculate sample's total seconds for the day.
        ts_seconds = (sample_ts - sample_ts.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()

        for x, y in self.generate_ranges(periods):
            if x <= ts_seconds and ts_seconds <= y:  # inclusive
                return True
        return False

    def generate_ranges(self, periods):
        for period in periods:
            start, end = (parse_duration(f'{x}:00') for x in period)
            yield (start.seconds, end.seconds)


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

    if return_type == 'select':

        # For a multi-select option we return the Event's value as a member of a list.
        def f(self):
            return [self.event.details.get(key),]

        # Assume 'select_multiple'
        return variables.select_multiple_rule_variable(label, options=optionslist)(f)

    def f(self):
        return self.event.details.get(key)

    if return_type == str:
        return variables.string_rule_variable(label)(f)
    elif return_type in (int, float):
        return variables.numeric_rule_variable(label)(f)
    else:
        raise NotImplementedError(f'Return-type {return_type} is not yet supported.')


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


def generate_global_event_variables(event_types):
    '''
    From a list of EventTypes, generate an EventVariables class adhering to Venmo business rules interface.
    :param event_type: A DAS EventType object that has a valid schema.
    :return: A `Variables` type to be used with Venmo business-rules package.
    '''

    applies_to_map = {}
    attributes_accumulator = {}
    # Render the EventType's schema.
    for event_type in event_types:
        rendered_schema = schema_utils.get_rendered_schema(event_type.schema)

        # Create an attributes list derived from schema and suitable for creating a Variables class.
        for k, v in rendered_schema['properties'].items():

            rule_return_type = translate_schema_type_to_type(v)
            if k in attributes_accumulator:
                print(f'Accumulator already has a {k} member. returning {rule_return_type}')
            attributes_accumulator.setdefault(k, (k, rule_return_type, v.get('title', k), genoptions(v)))

            applies_to_map.setdefault(k, []).append(event_type.value)

    attrs = dict((attr, create_new_func(attr, attrtype, label=label, optionslist=optionslist))
                  for attr, attrtype, label, optionslist in attributes_accumulator.values())

    # Invent a class name.
    classname = 'GlobalEventVariables'
    return type(classname, (EventVariables,), attrs), applies_to_map


def render_aggregate_eventvariables(event_types):

    variables_class, applies_to_map = generate_global_event_variables(event_types)

    rules = export_rule_data(variables_class, EventActions)

    # Annotate conditions with event-type information, and nudge operators into the place where the UI wants them.
    for item in rules['variables']:
        item['exclusive_to'] = applies_to_map.get(item['name'], None)

        if item['field_type'] not in ('select', 'select_multiple'):
            del item['options']  # Prune options attribute from non-select items.
    return rules



