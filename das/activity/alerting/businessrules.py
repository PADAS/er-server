import logging
from typing import Any, NamedTuple

from business_rules import actions, export_rule_data, fields, variables

from django.utils.translation import gettext as _

from activity.alerting.variables import case_insensitive_string_rule_variable
from activity.models import Event, EventDetails
from activity.permissions import EventCategoryPermissions
from activity.serializers import EventSerializer
from core.utils import NonHttpRequest
from observations.models import Subject, SubjectGroup
from utils import schema_utils

VIEW_SUBJECTGROUP_PERMS = ('observations.view_subjectgroup', )

# Use string value of priority as value (ex. '0') to satisfy rules engine.
priority_options = [dict(name=str(x), label=y)
                    for x, y in Event.PRIORITY_CHOICES]

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
        return self.event.get('title')

    @variables.select_multiple_rule_variable(label=_('Priority'), options=priority_options)
    def priority(self):
        return [str(self.event.get('priority')), ]

    @variables.select_multiple_rule_variable(label=_('State'), options=state_options)
    def state(self):
        return [self.event.get('inferred_state'), ]

    # TODO: Implement state-change logic.
    # @variables.select_multiple_rule_variable(label=_('State Change'), options=state_change_options)
    # def state_change(self):
    #     return [getattr(self.event, 'state_change', None), ]


class EventActions(actions.BaseActions):

    def __init__(self, event, action_list):
        self.event = event
        self.action_list = action_list

    @actions.rule_action(params={"alert_rule_id": fields.FIELD_NO_INPUT})
    def send_alert(self, alert_rule_id):
        logger.info(
            f'Sending alert for event {self.event["id"]} for alert_rule_id {alert_rule_id}.')
        self.action_list.append(
            dict(action='send_alert', event=self.event, alert_rule_id=alert_rule_id))


class RuleVariableSpec(NamedTuple):
    attrname: str
    return_type: Any
    label: str
    optionsdict: dict = dict


_WHITELISTED_OPERATORS = {
    fields.FIELD_NUMERIC: {
        'equal_to': '=',
        'greater_than': '>',
        'less_than': '<',
        # 'greater_than_or_equal_to': '>=',
        # 'less_than_or_equal_to': '<=',

        # TODO: Resolve how to include special characters here that will be
        # represented correctly inside a container.
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
                logger.debug(
                    f'For {vtypename} mapped {operator["name"]} to {label}')
                yield operator
    else:
        yield from operators


def create_subject_group_func(user=None):
    def f(self):
        return [str(subj_group.id) for subject in self.event.get('related_subjects') for subj_group in Subject.objects.get(id=subject.get('id')).groups.all()]

    options_list = []

    if user and user.has_any_perms(VIEW_SUBJECTGROUP_PERMS):
        options_list = [
            {
                'name': str(group.id),
                'label': group.name
            } for group in SubjectGroup.objects.all().filter(
                permission_sets__in=user.get_all_permission_sets()).distinct('id')
        ]
        options_list = sorted(options_list, key=lambda x: x['label'])
    return variables.select_multiple_rule_variable("Subject Group", options=options_list)(f)


def create_new_func(key, return_type, label=None, options_dict=None):
    '''
    Create a wrapped function for the given key and return-type.
    :param key: This identifies the key for the Event.details value. It is also used as the function's attribute name.
    :param return_type: The function's return-type -- it determines which business-rules decorator to use.
    :param label: The human friendly name for this variable.
    :param options_dict: None or a list of `{name: n, label: l}` dicts, derived from enumNames if available.
    :return: A getter function that's decorated with an appropriate business-rules @variables decorator.
    '''
    label = label or key.replace('_', ' ').title()

    if return_type == 'select':

        # For a multi-select option we return the Event's value as a member of
        # a list.
        def f(self):
            try:
                # there are still some dynamic choices where the value stored
                # in event_details is the UUID
                value = self.event['event_details'].get(key, {})
                if isinstance(value, dict):
                    value = value.get('value')
                return [value, ]
            except KeyError:
                return []

        options_list = list({'name': k, 'label': v}
                            for k, v in options_dict.items())
        options_list = sorted(options_list, key=lambda x: x['label'])
        return variables.select_multiple_rule_variable(label, options=options_list)(f)

    def string_f(self):
        event_details = self.event.get('event_details') or {}
        saved_value = event_details.get(key, '')
        return str(saved_value)

    def numeric_f(self):
        event_details = self.event.get('event_details') or {}
        saved_value = event_details.get(key, 0)

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
        raise NotImplementedError(
            f'Return-type {return_type} is not yet supported.')


def translate_schema_type_to_type(option):

    if 'enumNames' in option:
        return 'select'

    if 'type' not in option:
        logger.warning(
            'No \'type\' present in option, so using str. option=%s', option)
        return str

    if option['type'] == 'string':
        return str

    elif option['type'] == 'number':
        return int

    else:
        raise NotImplementedError(
            f'I don\'t support type \'{option["type"]}\' yet.')


def accumulate_options(schema_option, accumulator=None):
    '''
    Transform an Event-Type choice list from `enumNames` to business-rules friendly list.
    :param schema_option:
    :return:
    '''

    if 'enumNames' not in schema_option:
        return accumulator or {}

    elif accumulator is not None:
        for k, v in schema_option['enumNames'].items():
            if k not in accumulator:
                accumulator['k'] = v
        return accumulator
    else:
        try:
            return dict((k, v) for k, v in schema_option['enumNames'].items())
        except AttributeError:
            logger.exception('Failed to parse options for schema_option. I expected a dictionary but got %s',
                             schema_option)

    return {}


def _generate_aggregate_event_variables_class(event_types, only_common_factors=False, user=None):
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
        try:
            rendered_schema = schema_utils.get_rendered_schema(
                event_type.schema)
        except Exception as ex:
            logger.warn(
                f"Error in get_rendered_schema with {event_type.value}, ex:{ex}")
            raise

        keyset = set(rendered_schema['properties'].keys())
        keyset_list.append(keyset)
        logger.debug('event_type: %s - Adding keyset: %s',
                     event_type.value, keyset)

        # Accumulate rendered schema properties in a dict.
        schema_properties_map[event_type.value] = rendered_schema.get(
            'properties', {})

    # Determine intersection of keys.
    if only_common_factors:
        keyset_intersection = set.intersection(*keyset_list)
        logger.debug('Keyset intersection: %s', keyset_intersection)

    attributes_accumulator = {}
    applies_to_map = {}
    for event_type_value, schema_properties in schema_properties_map.items():

        # Create an attributes list derived from schema and suitable for
        # creating a Variables class.
        for k, v in schema_properties.items():

            if only_common_factors and k not in keyset_intersection:
                continue

            try:
                rule_return_type = translate_schema_type_to_type(v)
            except NotImplementedError:
                continue

            existing_attr = attributes_accumulator.get(k, None)
            if existing_attr:
                dummy = accumulate_options(v)
                print(f'{event_type_value}.{k} options = {list(dummy.keys())}')
                if existing_attr.return_type == rule_return_type:
                    accumulate_options(v, existing_attr.optionsdict)
                else:
                    logger.warning(
                        'Name collision on %s with different return types.', k)
            else:

                newattr = RuleVariableSpec(attrname=k, return_type=rule_return_type,
                                           label=v.get('title', k), optionsdict=accumulate_options(v))
                attributes_accumulator[k] = newattr

            applies_to_map.setdefault(k, []).append(event_type_value)

    attrs = dict((x.attrname, create_new_func(x.attrname, x.return_type, label=x.label, options_dict=x.optionsdict))
                 for x in attributes_accumulator.values())
    subject_group_func = create_subject_group_func(user)
    attrs['subject_group'] = subject_group_func

    # Invent a class name
    # TODO: Research the behavior of new-ing up a type like this repeatedly.
    classname = 'GlobalEventVariables'
    return type(classname, (EventVariables,), attrs), applies_to_map


PRUNE_OPTIONS_FROM = (
    fields.FIELD_TEXT, fields.FIELD_NO_INPUT, fields.FIELD_NUMERIC,)


def render_aggregate_event_variables(event_types, only_common_factors=False, user=None):
    '''
    From a list of EventTypes, generate render a set of rules.
    :param event_types: A list of DAS EventType objects from which to build a variables type.
    :param only_common_factors: Whether to reduce the list of variables to just those which apply to all event_types.
    :return: A rules document that the UI will render allowing a user to build a condition set.
    '''
    variables_class, applies_to_map = _generate_aggregate_event_variables_class(event_types,
                                                                                only_common_factors=only_common_factors, user=user)

    rules = export_rule_data(variables_class, EventActions)

    replacement_operators = {}
    for k, v in rules['variable_type_operators'].items():
        replacement_operators[k] = whitelist_operators(k, v)

    rules['variable_type_operators'] = replacement_operators

    # Annotate conditions with event-type information, and nudge operators
    # into the place where the UI wants them.
    for item in rules['variables']:
        item['exclusive_to'] = applies_to_map.get(item['name'], None)

        if item['field_type'] in PRUNE_OPTIONS_FROM:
            del item['options']
    return rules


def render_event(event, user, method='GET'):
    # This is a covenience function to render an Event
    request = NonHttpRequest()
    request.method = method
    request.user = user

    if EventCategoryPermissions().has_object_permission(request, None, event):
        event_data = EventSerializer(
            event, context={'request': request, }).data
        event_data['inferred_state'] = infer_event_state(event)
        return event_data
    else:
        logger.info(
            f'Permission denied when rendering event {event.serial_number} for user {user}.')
        return None


def infer_event_state(event):
    '''
    When state is not 'resolved', it can be coerced to 'active' if its latest revision is 'updated'.
    :return: an inferred state (one of 'new', 'active', 'resolved')
    '''

    if event.state in (Event.SC_RESOLVED, Event.SC_ACTIVE):
        return event.state

    event_revision, details_revision = resolve_event_revisions(event)
    inferred_state = Event.SC_NEW if event_revision and event_revision.action == 'added' else Event.SC_ACTIVE
    return inferred_state


def resolve_event_revisions(event):
    '''
    We end up in this code path in a few ways. Some data associated with the
    event has changed, but it could be the event itself or the event_details
    which contains the schema data. Or it could be both. It all depends on
    what fields were changed in the event update.

    To figure out what change(s) brought us here, we need to look at the
    timestamps on the latest revisions to both the event and eventdetails
    objects and see which one is newer.

    :param event_id:
    :return:
    '''
    revision = event.revision.all_user().latest('revision_at')
    try:
        details_revision = event.event_details.latest('updated_at') \
            .revision.all_user().latest('revision_at')
    except (AttributeError, EventDetails.DoesNotExist):
        return revision, None

    diff = (revision.revision_at - details_revision.revision_at).total_seconds()

    # If the timestamps are < 1 second apart, they were very likely made
    # together
    if abs(diff) < 1:
        return revision, details_revision
    # If the changes are farther apart, take the later one only
    elif diff < 0:
        return None, details_revision
    else:
        return revision, None
