from dataclasses import dataclass

import pytest

from utils.models import getattr_jsonfield


@dataclass
class JSONfieldTester:
    data: dict


class TestGetattrJsonfield:
    def test_getattr_jsonfield(self):
        obj = JSONfieldTester(data="John")
        obj = getattr_jsonfield(obj, "data")
        assert "John" == obj

    def test_key(self):
        obj = JSONfieldTester(data={"name": "John"})
        obj = getattr_jsonfield(obj, "data__name")
        assert "John" == obj

    def test_key_key(self):
        obj = JSONfieldTester(data={"level_one": {"level_two": "value_two"}})
        obj = getattr_jsonfield(obj, "data__level_one__level_two")
        assert "value_two" == obj

    def test_key_array(self):
        obj = JSONfieldTester(data={"level_one": ["value_array"]})
        obj = getattr_jsonfield(obj, "data__level_one__0")
        assert "value_array" == obj

    def test_key_array_key(self):
        obj = JSONfieldTester(data={"level_one": [{"level_three": "value_three"}]})
        obj = getattr_jsonfield(obj, "data__level_one__0__level_three")
        assert "value_three" == obj

    def test_key_array_key_raises_index_error(self):
        with pytest.raises(IndexError):
            obj = JSONfieldTester(data={"level_one": [{"level_three": "value_three"}]})
            obj = getattr_jsonfield(obj, "data__level_one__2__level_three")

    def test_key_array_key_raises_key_error(self):
        with pytest.raises(KeyError):
            obj = JSONfieldTester(data={"level_one": [{"level_three": "value_three"}]})
            obj = getattr_jsonfield(obj, "data__level_two__0__level_three")

    def test_key_array_key_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            obj = JSONfieldTester(data={"level_one": [{"level_three": "value_three"}]})
            obj = getattr_jsonfield(obj, "dataOne__level_one__0__level_three")

    def test_key_not_found_default_value(self):
        obj = JSONfieldTester(data={"name": "John"})
        obj = getattr_jsonfield(obj, "data__user", "James")
        assert "James" == obj

    def test_key_key_none(self):
        obj = JSONfieldTester(data={"level_one": {"level_two": None}})
        obj = getattr_jsonfield(obj, "data__level_one__level_two")
        assert obj is None

    def test_key_returns_array(self):
        array = [1, 2, 3, 4]
        obj = JSONfieldTester(data={"level_one": array})
        obj = getattr_jsonfield(obj, "data__level_one")
        assert array == obj

    def test_invalid_number_arguments(self):
        with pytest.raises(TypeError):
            obj = JSONfieldTester(data={"level_one": [{"level_three": "value_three"}]})
            obj = getattr_jsonfield(obj, "dataOne__level_one__0__level_three", None, None)
