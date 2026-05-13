import logging
from typing import Any, Dict, NamedTuple

from business_rules import actions, export_rule_data, fields, variables
from business_rules.operators import (
    BooleanType,
    NumericType,
    SelectMultipleType,
    StringType,
)

from django.utils.translation import gettext as _

from activity.alerting.schema_properties import AlertingSchemaPropertiesAdapter
from activity.alerting.variables import (
    MultiSelectChoiceType,
    case_insensitive_string_rule_variable,
    multi_select_choice_rule_variable,
)
from activity.models import Event
from observations.models import Subject, SubjectGroup

VIEW_SUBJECTGROUP_PERMS = ("observations.view_subjectgroup",)

# Use string value of priority as value (ex. '0') to satisfy rules engine.
priority_options = [dict(name=str(x), label=y) for x, y in Event.PRIORITY_CHOICES]

state_options = [dict(name=x, label=y) for x, y in Event.STATE_CHOICES]

state_change_options = [
    {
        "name": "new",
        "label": "New",
    },
    {
        "name": "updated",
        "label": "Updated",
    },
    {
        "name": "resolved",
        "label": "Resolved",
    },
]

logger = logging.getLogger(__name__)


class EventVariables(variables.BaseVariables):
    def __init__(self, event):
        self.event = event

    @case_insensitive_string_rule_variable(label=_("Title"))
    def title(self):
        return self.event.get("title")

    @variables.select_multiple_rule_variable(label=_("Priority"), options=priority_options)
    def priority(self):
        return [
            str(self.event.get("priority")),
        ]

    @variables.select_multiple_rule_variable(label=_("State"), options=state_options)
    def state(self):
        return [
            self.event.get("inferred_state"),
        ]

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
        logger.info(f'Sending alert for event {self.event["id"]} for alert_rule_id {alert_rule_id}.')
        self.action_list.append(dict(action="send_alert", event=self.event, alert_rule_id=alert_rule_id))


class RuleVariableSpec(NamedTuple):
    attrname: str
    return_type: Any
    label: str
    optionsdict: dict | None = None


# Keyed by type name (BaseType.name) — the same keys that export_rule_data
# puts into variable_type_operators. Do NOT confuse with fields.FIELD_*
# constants, which are operator *input widget* identifiers.
_WHITELISTED_OPERATORS = {
    NumericType.name: {
        "equal_to": "=",
        "greater_than": ">",
        "less_than": "<",
        # 'greater_than_or_equal_to': '>=',
        # 'less_than_or_equal_to': '<=',
        # TODO: Resolve how to include special characters here that will be
        # represented correctly inside a container.
        "greater_than_or_equal_to": "≥",
        "less_than_or_equal_to": "≤",
    },
    # Single-select fields (V1 and V2) wrap their value in a list so the
    # library's set-comparison operators work as "is one of".
    SelectMultipleType.name: {
        "shares_at_least_one_element_with": "Is One Of",
        "shares_no_elements_with": "Is Not One Of",
    },
    # V2 multi-select choice fields that store native lists.
    MultiSelectChoiceType.name: {
        "contains": "Contains",
        "is_exactly": "Is Exactly",
        "is_empty": "Is Empty",
        "is_not_empty": "Is Not Empty",
        "is_one_of": "Is One Of",
        "is_not_one_of": "Is Not One Of",
    },
    BooleanType.name: {
        "is_true": "Is True",
        "is_false": "Is False",
    },
    StringType.name: {
        "contains": "Includes",
        "non_empty": "Is Not Empty",
    },
}


def whitelist_operators(vtypename, operators):
    wtype = _WHITELISTED_OPERATORS.get(vtypename)
    if wtype:
        for operator in operators:
            label = wtype.get(operator["name"])
            if label:
                operator["label"] = label
                logger.debug(f'For {vtypename} mapped {operator["name"]} to {label}')
                yield operator
    else:
        yield from operators


def create_subject_group_func(user=None):
    def f(self):
        return [
            str(subj_group.id)
            for subject in self.event.get("related_subjects")
            for subj_group in Subject.objects.get(id=subject.get("id")).get_ancestor_subject_groups()
        ]

    options_list = []

    if user and user.has_any_perms(VIEW_SUBJECTGROUP_PERMS):
        options_list = [
            {"name": str(group.id), "label": group.name}
            for group in SubjectGroup.objects.all()
            .filter(permission_sets__in=user.get_all_permission_sets())
            .distinct("id")
        ]
        options_list = sorted(options_list, key=lambda x: x["label"])
    return variables.select_multiple_rule_variable("Subject Group", options=options_list)(f)


def create_new_func(key, return_type, label=None, options_dict=None):
    """
    Create a wrapped function for the given key and return-type.
    :param key: This identifies the key for the Event.details value. It is also used as the function's attribute name.
    :param return_type: The function's return-type -- it determines which business-rules decorator to use.
    :param label: The human friendly name for this variable.
    :param options_dict: None or a list of `{name: n, label: l}` dicts, derived from enumNames if available.
    :return: A getter function that's decorated with an appropriate business-rules @variables decorator.
    """
    label = label or key.replace("_", " ").title()

    if return_type == "select":
        # For a multi-select option we return the Event's value as a member of
        # a list.
        def f(self):
            event_details = self.event.get("event_details") or {}
            value = event_details.get(key, {})
            if isinstance(value, dict):
                value = value.get("value")
            return [value]

        options_list = list({"name": k, "label": v} for k, v in options_dict.items())
        options_list = sorted(options_list, key=lambda x: x["label"])
        return variables.select_multiple_rule_variable(label, options=options_list)(f)

    if return_type == "multiselect":

        def multi_f(self):
            event_details = self.event.get("event_details") or {}
            value = event_details.get(key, [])
            if isinstance(value, dict):
                value = value.get("value", [])
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return value
            return []

        options_list = list({"name": k, "label": v} for k, v in options_dict.items())
        options_list = sorted(options_list, key=lambda x: x["label"])
        return multi_select_choice_rule_variable(label, options=options_list)(multi_f)

    def string_f(self):
        event_details = self.event.get("event_details") or {}
        saved_value = event_details.get(key, "")
        return str(saved_value)

    def numeric_f(self):
        event_details = self.event.get("event_details") or {}
        saved_value = event_details.get(key, 0)

        if isinstance(saved_value, (str,)):
            if "." in saved_value:
                return float(saved_value)
            else:
                return int(saved_value)
        else:
            return saved_value

    if return_type == bool:

        def bool_f(self):
            event_details = self.event.get("event_details") or {}
            return bool(event_details.get(key, False))

        return variables.boolean_rule_variable(label)(bool_f)

    if return_type == str:
        return case_insensitive_string_rule_variable(label)(string_f)
    elif return_type in (int, float):
        return variables.numeric_rule_variable(label)(numeric_f)
    else:
        raise NotImplementedError(f"Return-type {return_type} is not yet supported.")


_CHOICE_MARKERS = ("enumNames", "enum", "anyOf", "oneOf")

_SCHEMA_TYPE_TO_RULE_TYPE = {
    "select": "select",
    "multiselect": "multiselect",
    "string": str,
    "number": int,
    "integer": int,
    "boolean": bool,
}


def get_schema_type(option: Dict[str, str]) -> str:
    """Canonical schema-type detection for a single field property dict.

    Returns a string type identifier: 'select', 'multiselect', 'string', 'number', etc.
    """
    if any(key in option for key in _CHOICE_MARKERS):
        return "select"

    if option.get("type") == "array":
        items = option.get("items", {})
        if any(key in items for key in _CHOICE_MARKERS):
            return "multiselect"

    if "type" not in option:
        return "string"

    return option["type"]


def translate_schema_type_to_type(option):
    """Map a schema field to a business-rules return type.

    Delegates to get_schema_type for detection, then maps the string result
    to the Python type or string expected by create_new_func.
    """
    schema_type = get_schema_type(option)
    rule_type = _SCHEMA_TYPE_TO_RULE_TYPE.get(schema_type)
    if rule_type is not None:
        return rule_type
    raise NotImplementedError(f"I don't support type '{schema_type}' yet.")


def remove_field_suffix(input_string: str) -> str:
    # Find the last occurrence of '_' in the string
    last_underscore_index = input_string.rfind("_")

    if last_underscore_index != -1:
        # If '_' is found, return the substring before '_'
        return input_string[:last_underscore_index]

    # If '_' is not found, return the original string
    return input_string


def _generate_aggregate_event_variables_class(
    event_types, request=None, only_common_factors=False, support_legacy_event_variables=False
):
    """
    From a list of EventTypes, generate an EventVariables class adhering to business-rules interface.
    :param event_types: A list of DAS EventType objects from which to build a variables type.
    :param request: Optional DRF request object. If None, a synthetic superuser request
                   is created to ensure all schema options are available for alert rule evaluation.
    :param only_common_factors: Whether to reduce the list of variables to just those which apply to all event_types.
    :param support_legacy_event_variables: Whether to support legacy event variables.
    :return: A `Variables` type to be used with Venmo business-rules package.
    """

    supported_field_attributes = ["no_legacy"] + (["legacy"] if support_legacy_event_variables else [])

    schema_properties_map = {}
    schema_properties_adapter = AlertingSchemaPropertiesAdapter()

    # Reduce schemas to common properties
    keyset_list = []
    for event_type in event_types:
        try:
            properties_result = schema_properties_adapter.get_alert_properties(event_type, request)
            if properties_result.status == "failure":
                logger.warning("Schema processing failed for %s: %s", event_type.value, properties_result.errors)
                continue

            properties = properties_result.properties
            keyset = set(properties.keys())
            keyset_list.append(keyset)

            # Accumulate rendered schema properties and choice options
            schema_properties_map[event_type.value] = properties_result

        except Exception as ex:
            logger.warning("Error processing schema for %s, ex:%s", event_type.value, ex)
            raise

    # Determine intersection of keys.
    if only_common_factors:
        keyset_intersection = set.intersection(*keyset_list)

    attributes_accumulator = {}
    applies_to_map = {}
    for event_type_value, properties_result in schema_properties_map.items():
        # Create an attributes list derived from schema and suitable for creating a Variables class.
        for field_name, field_properties in properties_result.properties.items():
            if only_common_factors and field_name not in keyset_intersection:
                continue

            try:
                rule_return_type = translate_schema_type_to_type(field_properties)
            except NotImplementedError:
                continue

            composite_key = field_name + "_" + get_schema_type(field_properties)
            existing_attr = attributes_accumulator.get(composite_key, None)
            field_choice_options = properties_result.choice_options_map.get(field_name, {})
            if existing_attr:
                logger.debug("%s.%s options = %s", event_type_value, composite_key, list(field_choice_options.keys()))
                if existing_attr.return_type == rule_return_type:
                    # Merge choice options into existing attribute
                    merged = dict(existing_attr.optionsdict or {})
                    merged.update(field_choice_options)
                    attributes_accumulator[composite_key] = existing_attr._replace(optionsdict=merged)
                else:
                    logger.warning(
                        "Collision on %s with different return types. Adding a new object with different return type",
                        field_name,
                    )
                    newattr = RuleVariableSpec(
                        attrname=field_name,
                        return_type=rule_return_type,
                        label=field_properties.get("title", field_name),
                        optionsdict=field_choice_options,
                    )
                    attributes_accumulator[composite_key] = newattr
            else:
                newattr = RuleVariableSpec(
                    attrname=field_name,
                    return_type=rule_return_type,
                    label=field_properties.get("title", field_name),
                    optionsdict=field_choice_options,
                )
                attributes_accumulator[composite_key] = newattr

            applies_to_map.setdefault(composite_key, []).append(event_type_value)

    attrs = {
        (
            composite_field_name if key_suffix == "no_legacy" else remove_field_suffix(composite_field_name)
        ): create_new_func(
            field_properties.attrname,
            field_properties.return_type,
            label=field_properties.label,
            options_dict=field_properties.optionsdict,
        )
        for composite_field_name, field_properties in attributes_accumulator.items()
        for key_suffix in supported_field_attributes
    }

    user = getattr(request, "user", None) if request else None
    subject_group_func = create_subject_group_func(user)
    attrs["subject_group"] = subject_group_func

    # Invent a class name
    # TODO: Research the behavior of new-ing up a type like this repeatedly.
    classname = "GlobalEventVariables"
    return type(classname, (EventVariables,), attrs), applies_to_map


# Type names whose variables should not carry options to the UI.
# Compared against item["field_type"], which is BaseType.name.
PRUNE_OPTIONS_FROM = (
    StringType.name,
    NumericType.name,
    BooleanType.name,
)


def render_aggregate_event_variables(event_types, request, only_common_factors=False):
    """
    From a list of EventTypes, generate render a set of rules.
    :param event_types: A list of DAS EventType objects from which to build a variables type.
    :param only_common_factors: Whether to reduce the list of variables to just those which apply to all event_types.
    :param request: DRF request object (needed for V2 EventType processing).
    :return: A rules document that the UI will render allowing a user to build a condition set.
    """
    variables_class, applies_to_map = _generate_aggregate_event_variables_class(
        event_types, request=request, only_common_factors=only_common_factors
    )

    rules = export_rule_data(variables_class, EventActions)

    replacement_operators = {}
    for k, v in rules["variable_type_operators"].items():
        replacement_operators[k] = whitelist_operators(k, v)

    rules["variable_type_operators"] = replacement_operators

    # Annotate conditions with event-type information, and nudge operators
    # into the place where the UI wants them.
    for item in rules["variables"]:
        item["exclusive_to"] = applies_to_map.get(item["name"], None)

        if item["field_type"] in PRUNE_OPTIONS_FROM:
            del item["options"]
    return rules
