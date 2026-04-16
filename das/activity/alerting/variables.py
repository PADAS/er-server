import re

import business_rules.fields
import business_rules.operators
from business_rules.fields import FIELD_NO_INPUT, FIELD_SELECT_MULTIPLE, FIELD_TEXT
from business_rules.operators import export_type, type_operator
from business_rules.variables import BaseType, rule_variable

# -- Custom type names -------------------------------------------------------
# These identify our custom BaseType subclasses in the business-rules engine.
# They are assigned to the `name` attribute of each type class and registered
# into ``business_rules.fields`` at module load time.
TYPE_NAME_CI_STRING = "ci_string"
TYPE_NAME_MULTI_SELECT_CHOICE = "multi_select_choice"


@export_type
class CaseInsensitiveStringType(BaseType):

    name = TYPE_NAME_CI_STRING

    def _assert_valid_value_and_cast(self, value):
        value = value or ""
        if not isinstance(value, (str,)):
            raise AssertionError("{0} is not a valid string type.".format(value))
        return value

    @type_operator(FIELD_TEXT)
    def equal_to(self, other_string):
        return self.value.lower() == other_string.lower()

    @type_operator(FIELD_TEXT, label="Equal To (case insensitive)")
    def equal_to_case_insensitive(self, other_string):
        return self.value.lower() == other_string.lower()

    @type_operator(FIELD_TEXT)
    def starts_with(self, other_string):
        return self.value.lower().startswith(other_string.lower())

    @type_operator(FIELD_TEXT)
    def ends_with(self, other_string):
        return self.value.lower().endswith(other_string.lower())

    @type_operator(FIELD_TEXT)
    def contains(self, other_string):
        return other_string.lower() in self.value.lower()

    @type_operator(FIELD_TEXT)
    def matches_regex(self, regex):
        return re.search(regex, self.value)

    @type_operator(FIELD_NO_INPUT)
    def non_empty(self):
        return bool(self.value)


def case_insensitive_string_rule_variable(label=None):
    return rule_variable(CaseInsensitiveStringType, label=label)


business_rules.operators.CaseInsensitiveStringType = CaseInsensitiveStringType


@export_type
class MultiSelectChoiceType(BaseType):
    """Business-rules type for multi-select choice fields (V2 choice_list).

    Handles values that are already lists (e.g. ["val1", "val2"]).
    """

    name = TYPE_NAME_MULTI_SELECT_CHOICE

    def _assert_valid_value_and_cast(self, value):
        if value is None:
            return []
        if isinstance(value, dict):
            inner = value.get("value")
            return [inner] if inner else []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        raise AssertionError(f"{value} is not a valid multi-select type")

    @type_operator(FIELD_SELECT_MULTIPLE, label="Contains")
    def contains(self, other_value):
        """All values in other_value are present in the selection."""
        for val in other_value:
            if val not in self.value:
                return False
        return True

    @type_operator(FIELD_SELECT_MULTIPLE, label="Is Exactly")
    def is_exactly(self, other_value):
        """Selected values match the given set exactly."""
        return set(self.value) == set(other_value)

    @type_operator(FIELD_NO_INPUT, label="Is Empty")
    def is_empty(self):
        """No values are selected."""
        return len(self.value) == 0

    @type_operator(FIELD_NO_INPUT, label="Is Not Empty")
    def is_not_empty(self):
        """At least one value is selected."""
        return len(self.value) > 0

    @type_operator(FIELD_SELECT_MULTIPLE, label="Is One Of")
    def is_one_of(self, other_value):
        """At least one selected value is in the given set."""
        return any(val in other_value for val in self.value)

    @type_operator(FIELD_SELECT_MULTIPLE, label="Is Not One Of")
    def is_not_one_of(self, other_value):
        """No selected value is in the given set."""
        return not self.is_one_of(other_value)


def multi_select_choice_rule_variable(label=None, options=None):
    return rule_variable(MultiSelectChoiceType, label=label, options=options)


business_rules.operators.MultiSelectChoiceType = MultiSelectChoiceType
business_rules.fields.FIELD_MULTI_SELECT_CHOICE = TYPE_NAME_MULTI_SELECT_CHOICE
