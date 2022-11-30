from collections import OrderedDict

import pytest

from utils.schema_utils import extract_from_dict_or_string


@pytest.mark.django_db
class TestSchemaUtils:
    def test_extract_from_dict_or_string_function(self):
        enum_names = OrderedDict()
        enum_names["d2c4fe5b-5bfd-42b7-848e-4320abc395b5"] = "Caballo prieto Azabache"
        enum_names["fa5cf4ab-e3af-47de-94ed-0f0b729cd71a"] = "Alazan"
        enum_names["43242bac-5ec6-43b2-9daf-5a6888c00733"] = "El giro"

        schema_item = OrderedDict()
        schema_item["type"] = "string"
        schema_item["title"] = "Hello"
        schema_item["enum"] = [
            "d2c4fe5b-5bfd-42b7-848e-4320abc395b5",
            "fa5cf4ab-e3af-47de-94ed-0f0b729cd71a",
            "43242bac-5ec6-43b2-9daf-5a6888c00733",
        ]
        schema_item["enumNames"] = enum_names

        value, display = extract_from_dict_or_string(schema_item, "43242bac-5ec6-43b2-9daf-5a6888c00733")

        assert value == "43242bac-5ec6-43b2-9daf-5a6888c00733"
        assert display == "El giro"

    def test_extract_from_dict_or_string_for_an_inactive_subject(self, subject):
        subject.is_active = False
        subject.name = "Heisenberg"
        subject.save()
        enum_names = OrderedDict()
        enum_names["d2c4fe5b-5bfd-42b7-848e-4320abc395b5"] = "Caballo prieto Azabache"
        schema_item = OrderedDict()
        schema_item["type"] = "string"
        schema_item["title"] = "Hello"
        schema_item["enum"] = [
            "d2c4fe5b-5bfd-42b7-848e-4320abc395b5",
        ]
        schema_item["enumNames"] = enum_names

        value, display = extract_from_dict_or_string(schema_item, f"{subject.id}")

        assert value == f"{subject.id}"
        assert display == "Heisenberg"

    @pytest.mark.parametrize(
        ("mocked_date", "expected_display"),
        (
            ("2022-10-28T12:00:00.000Z", "2022-10-28 12:00"),
            ("2022-01-25T12:00:00.000Z", "2022-01-25 12:00"),
            ("2022-10-Z", "2022-10-Z"),
            ("-27.151221,-101", "-27.151221,-101"),
        ),
    )
    def test_extract_from_dict_or_string_function_date_string_parsing(self, mocked_date, expected_display):
        schema_item = OrderedDict([("type", "string"), ("title", "Time when shot was heard")])

        _, display = extract_from_dict_or_string(schema_item, mocked_date)

        assert display == expected_display
