from business_rules.variables import BaseType, SelectType, rule_variable
import business_rules.operators
from business_rules.operators import export_type, type_operator

FIELD_ALT_SELECT_MULTIPLE = 'alt_select_multiple'


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
