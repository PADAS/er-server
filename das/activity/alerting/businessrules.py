from typing import NamedTuple, Any

from core.utils import NonHttpRequest
from activity.serializers import EventSerializer

from utils import schema_utils
from business_rules import actions, fields, variables, export_rule_data

from activity.alerting.variables import case_insensitive_string_rule_variable

from django.utils.translation import ugettext as _

import logging

from activity.models import Event

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

    @case_insensitive_string_rule_variable(label=_('Title'))
    def title(self):
        return self.event.get('title') or self.event

    @variables.select_multiple_rule_variable(label=_('Priority'), options=priority_options)
    def priority(self):
        return [str(self.event.get('priority')),]

    @variables.select_multiple_rule_variable(label=_('State'), options=state_options)
    def state(self):
        return [self.event.get('state'),]

    @variables.select_multiple_rule_variable(label=_('State Change'), options=state_change_options)
    def state_change(self):
        return [getattr(self.event, 'state_change', None), ]


class EventActions(actions.BaseActions):

    def __init__(self, event, action_list):
        self.event = event
        self.action_list = action_list

    @actions.rule_action(params={"alert_rule_id": fields.FIELD_NO_INPUT})
    def send_alert(self, alert_rule_id):
        logger.info(f'Sending alert for event {self.event["id"]} for alert_rule_id {alert_rule_id}.')
        self.action_list.append(dict(action='send_alert', event=self.event, alert_rule_id=alert_rule_id))


class RuleVariableSpec(NamedTuple):
    attrname: str
    return_type: Any
    label: str
    optionslist: list


_WHITELISTED_OPERATORS = {
    fields.FIELD_NUMERIC: {
        'equal_to': '=',
        'greater_than': '>',
        'less_than': '<',
        # 'greater_than_or_equal_to': '>=',
        # 'less_than_or_equal_to': '<=',

        # TODO: Resolve how to include special characters here that will be represented correctly inside a container.
        'greater_than_or_equal_to': '≥',
        'less_than_or_equal_to': '≤',
    },

    fields.FIELD_SELECT_MULTIPLE: {
        'shares_at_least_one_element_with': 'Is One Of',
        'shares_no_elements_with': 'Is Not One Of'
    },

    'string': {
        'contains': 'Includes',
        'non_empty': 'Is Not Empty',
    }
}


def whitelist_operators(vtypename, operators):

    wtype = _WHITELISTED_OPERATORS.get(vtypename)
    if wtype:
        for operator in operators:
            label = wtype.get(operator['name'])
            if label:
                operator['label'] = label
                logger.debug(f'For {vtypename} mapped {operator["name"]} to {label}')
                yield operator
    else:
        yield from operators


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
            try:
                return [self.event['event_details'][key]['value'], ]
            except KeyError:
                return []

        optionslist = sorted(optionslist, key=lambda x: x['label'])
        return variables.select_multiple_rule_variable(label, options=optionslist)(f)

    def string_f(self):
        saved_value = self.event.get('event_details', {}).get(key, '')
        return str(saved_value)

    def numeric_f(self):
        saved_value = self.event.get('event_details', {}).get(key, 0)

        if isinstance(saved_value, (str,)):
            if '.' in saved_value:
                return float(saved_value)
            else:
                return int(saved_value)
        else:
            return saved_value

    if return_type == str:
        return case_insensitive_string_rule_variable(label)(string_f)
    elif return_type in (int, float):
        return variables.numeric_rule_variable(label)(numeric_f)
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


def generate_option_list(schema_option):
    '''
    Transform an Event-Type choice list from `enumNames` to business-rules friendly list.
    :param schema_option:
    :return:
    '''
    if 'enumNames' in schema_option:
        return [{'name': k, 'label': v} for k, v in schema_option['enumNames'].items()]
    return []


def _generate_aggregate_event_variables_class(event_types, only_common_factors=False):
    '''
    From a list of EventTypes, generate an EventVariables class adhering to business-rules interface.
    :param event_types: A list of DAS EventType objects from which to build a variables type.
    :param only_common_factors: Whether to reduce the list of variables to just those which apply to all event_types.
    :return: A `Variables` type to be used with Venmo business-rules package.
    '''

    schema_properties_map = {}

    # Reduce schemas to common properties
    keyset_list = []
    for event_type in event_types:

        rendered_schema = schema_utils.get_rendered_schema(event_type.schema)
        keyset = set(rendered_schema['properties'].keys())
        keyset_list.append(keyset)
        logger.debug('event_type: %s - Adding keyset: %s', event_type.value, keyset)

        # Accumulate rendered schema properties in a dict.
        schema_properties_map[event_type.value] = rendered_schema.get('properties', {})

    # Determine intersection of keys.
    if only_common_factors:
        keyset_intersection = set.intersection(*keyset_list)
        logger.debug('Keyset intersection: %s', keyset_intersection)

    attributes_accumulator = {}
    applies_to_map = {}
    for event_type_value, schema_properties in schema_properties_map.items():

        # Create an attributes list derived from schema and suitable for creating a Variables class.
        for k, v in schema_properties.items():

            if only_common_factors and k not in keyset_intersection:
                continue

            rule_return_type = translate_schema_type_to_type(v)

            newattr = RuleVariableSpec(attrname=k, return_type=rule_return_type,
                                       label=v.get('title', k), optionslist=generate_option_list(v))

            attr = attributes_accumulator.get(k, None)
            if attr:
                if attr.return_type == newattr.return_type:
                    attr.optionslist.extend(generate_option_list(v))
                else:
                    logger.warning('Name collision on %s with different return types.', k)
            else:
                attributes_accumulator[k] = newattr

            applies_to_map.setdefault(k, []).append(event_type_value)

    attrs = dict((x.attrname, create_new_func(x.attrname, x.return_type, label=x.label, optionslist=x.optionslist))
                 for x in attributes_accumulator.values())

    # Invent a class name
    # TODO: Research the behavior of new-ing up a type like this repeatedly.
    classname = 'GlobalEventVariables'
    return type(classname, (EventVariables,), attrs), applies_to_map


PRUNE_OPTIONS_FROM = (fields.FIELD_TEXT, fields.FIELD_NO_INPUT, fields.FIELD_NUMERIC,)


def render_aggregate_event_variables(event_types, only_common_factors=False):
    '''
    From a list of EventTypes, generate render a set of rules.
    :param event_types: A list of DAS EventType objects from which to build a variables type.
    :param only_common_factors: Whether to reduce the list of variables to just those which apply to all event_types.
    :return: A rules document that the UI will render allowing a user to build a condition set.
    '''

    variables_class, applies_to_map = _generate_aggregate_event_variables_class(event_types,
                                                                                only_common_factors=only_common_factors)

    rules = export_rule_data(variables_class, EventActions)

    replacement_operators = {}
    for k, v in rules['variable_type_operators'].items():
        replacement_operators[k] = whitelist_operators(k, v)

    rules['variable_type_operators'] = replacement_operators

    # Annotate conditions with event-type information, and nudge operators into the place where the UI wants them.
    for item in rules['variables']:
        item['exclusive_to'] = applies_to_map.get(item['name'], None)

        if item['field_type'] in PRUNE_OPTIONS_FROM:
            del item['options']
    return rules


def render_event(event, user):
    # This is a covenience function to render an Event
    request = NonHttpRequest()
    request.user = user
    return EventSerializer(event, context={'request': request,}).data
