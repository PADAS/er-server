"""Unit tests for activity.alerting.variables (custom business-rules types)."""

from activity.alerting.variables import MultiSelectChoiceType


class TestMultiSelectChoiceTypeOperators:
    """Unit tests for MultiSelectChoiceType operator logic."""

    def test_contains_all_present(self):
        mst = MultiSelectChoiceType(["bushmeat", "ivory", "timber"])
        assert mst.contains(["bushmeat", "ivory"]) is True

    def test_contains_some_missing(self):
        mst = MultiSelectChoiceType(["bushmeat", "timber"])
        assert mst.contains(["bushmeat", "ivory"]) is False

    def test_contains_empty_condition(self):
        mst = MultiSelectChoiceType(["bushmeat"])
        assert mst.contains([]) is True

    def test_is_exactly_match(self):
        mst = MultiSelectChoiceType(["bushmeat", "ivory"])
        assert mst.is_exactly(["ivory", "bushmeat"]) is True

    def test_is_exactly_no_match(self):
        mst = MultiSelectChoiceType(["bushmeat", "ivory"])
        assert mst.is_exactly(["bushmeat"]) is False

    def test_is_empty_true(self):
        mst = MultiSelectChoiceType([])
        assert mst.is_empty() is True

    def test_is_empty_false(self):
        mst = MultiSelectChoiceType(["bushmeat"])
        assert mst.is_empty() is False

    def test_is_not_empty_true(self):
        mst = MultiSelectChoiceType(["bushmeat"])
        assert mst.is_not_empty() is True

    def test_is_not_empty_false(self):
        mst = MultiSelectChoiceType([])
        assert mst.is_not_empty() is False

    def test_is_one_of_match(self):
        mst = MultiSelectChoiceType(["bushmeat", "timber"])
        assert mst.is_one_of(["ivory", "timber"]) is True

    def test_is_one_of_no_match(self):
        mst = MultiSelectChoiceType(["bushmeat", "timber"])
        assert mst.is_one_of(["ivory", "skins"]) is False

    def test_is_not_one_of_true(self):
        mst = MultiSelectChoiceType(["bushmeat", "timber"])
        assert mst.is_not_one_of(["ivory", "skins"]) is True

    def test_is_not_one_of_false(self):
        mst = MultiSelectChoiceType(["bushmeat", "timber"])
        assert mst.is_not_one_of(["ivory", "timber"]) is False

    def test_cast_none_to_empty_list(self):
        mst = MultiSelectChoiceType(None)
        assert mst.value == []

    def test_cast_dict_extracts_value(self):
        mst = MultiSelectChoiceType({"name": "Bush Meat", "value": "bushmeat"})
        assert mst.value == ["bushmeat"]

    def test_cast_string_to_single_list(self):
        mst = MultiSelectChoiceType("bushmeat")
        assert mst.value == ["bushmeat"]

    def test_cast_list_passthrough(self):
        mst = MultiSelectChoiceType(["a", "b"])
        assert mst.value == ["a", "b"]

    def test_is_one_of_empty_selection(self):
        """Empty selection should not match anything."""
        mst = MultiSelectChoiceType([])
        assert mst.is_one_of(["bushmeat"]) is False
