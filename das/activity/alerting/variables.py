import re

from business_rules.variables import BaseType, SelectType, rule_variable
import business_rules.operators
from business_rules.operators import export_type, type_operator

FIELD_ALT_SELECT_MULTIPLE = 'alt_select_multiple'

FIELD_CI_STRING = 'ci_string'

@export_type
class AltSelectMultipleType(BaseType):

    name = FIELD_ALT_SELECT_MULTIPLE

    def _assert_valid_value_and_cast(self, value):
        if not hasattr(value, '__iter__'):
            raise AssertionError("{0} is not a valid select multiple type".
                                 format(value))
        return value

    @type_operator(FIELD_ALT_SELECT_MULTIPLE, label='Is One Of')
    def shares_at_least_one_element_with(self, other_value):
        select = SelectType(self.value)
        for other_val in other_value:
            if select.contains(other_val):
                return True
        return False

    @type_operator(FIELD_ALT_SELECT_MULTIPLE, label='Is Not One Of')
    def shares_no_elements_with(self, other_value):
        return not self.shares_at_least_one_element_with(other_value)


def custom_select_multiple_rule_variable(label=None, options=None):
    return rule_variable(AltSelectMultipleType, label=label, options=options)

business_rules.operators.AltSelectMultipleType = AltSelectMultipleType

FIELD_TEXT = 'text'
FIELD_NO_INPUT = 'none'
@export_type
class CaseInsensitiveStringType(BaseType):

    name = FIELD_CI_STRING

    def _assert_valid_value_and_cast(self, value):
        value = value or ""
        if not isinstance(value, (str,)):
            raise AssertionError("{0} is not a valid string type.".
                                 format(value))
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
