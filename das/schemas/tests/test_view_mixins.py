import json

import pytest

from django.urls import reverse
from rest_framework.generics import ListAPIView

from schemas.tests.fixtures import MockDynamicSchemaView
from schemas.view_mixins import DynamicSchemaDataMixin, ENUM_EXTRA_KEY


@pytest.mark.django_db
class TestDynamicSchemaFromSourceView:

    def test_default_fields(self, superuser_client, add_view_to_urls):
        """
        When no override query params are passed,
        default_enum_field and default_display_field should be used.
        """
        url_name = add_view_to_urls(MockDynamicSchemaView)
        url = reverse(url_name)
        response = superuser_client.get(url)

        assert response.status_code == 200

        data = response.data
        extra = data[ENUM_EXTRA_KEY]
        assert data["enum"][0] == "uuid1"
        assert extra["uuid1"]["display"] == "John Doe"
        assert extra["uuid1"]["description"] == "A person"
        assert data["enum"][1] == "uuid2"
        assert extra["uuid2"]["display"] == "Brigitte Bardot"
        assert extra["uuid2"]["description"] == "Actress and singer"
        # extra_info should appear as info by default
        assert extra["uuid1"]["info"] == "foobar"
        # second item has no extra_info, so None is expected
        assert extra["uuid2"]["info"] is None

    def test_overridden_fields(self, superuser_client, add_view_to_urls):
        """
        Test passing s_enum, s_display, s_description, and enum_extra to override defaults.
        """
        url_name = add_view_to_urls(MockDynamicSchemaView)
        url = reverse(url_name)
        query_params = {
            "s_enum": "custom_id",
            "s_display": "age",
            "s_description": "country",
            "enum_extra": json.dumps({"icon": "extra_info", "lang": "language"}),
        }
        response = superuser_client.get(url, query_params)

        assert response.status_code == 200

        data = response.data
        extra = data[ENUM_EXTRA_KEY]
        assert data["enum"][0] == "custom_uuid1"
        assert extra["custom_uuid1"]["display"] == 30
        assert extra["custom_uuid1"]["description"] == "USA"
        assert data["enum"][1] == "custom_uuid2"
        assert extra["custom_uuid2"]["display"] == 25
        assert extra["custom_uuid2"]["description"] == "France"
        assert extra["custom_uuid1"]["lang"] == "en"
        assert extra["custom_uuid1"]["icon"] == "foobar"
        assert extra["custom_uuid2"]["lang"] == "fr"
        assert extra["custom_uuid2"]["icon"] is None

    def test_custom_getter_method(self, superuser_client, add_view_to_urls):
        """
        Test a custom getter method that modifies the bio field.
        """

        class CustomDynamicSchemaView(MockDynamicSchemaView):
            """Just adds a custom getter method in the format get_<field_name>_from_item"""

            def get_better_bio_from_item(self, item: dict) -> str:
                return f"{item.get('bio')}, {item.get('age')} years old"

        url_name = add_view_to_urls(CustomDynamicSchemaView, route="custom-schema", name="custom-schema")
        url = reverse(url_name)
        response = superuser_client.get(url, {"s_description": "better_bio"})

        assert response.status_code == 200

        extra = response.data[ENUM_EXTRA_KEY]
        assert extra["uuid1"]["description"] == "A person, 30 years old"
        assert extra["uuid2"]["description"] == "Actress and singer, 25 years old"

    def test_custom_getter_method_has_precedence(self, superuser_client, add_view_to_urls):
        """
        Test that a custom getter method takes precedence over the default description field.
        """

        class CustomDynamicSchemaView(MockDynamicSchemaView):
            def get_bio_from_item(self, item: dict) -> str:
                return f"{item.get('bio')}, {item.get('age')} years old"

        url_name = add_view_to_urls(CustomDynamicSchemaView, route="test-schema", name="test-schema")
        url = reverse(url_name)
        response = superuser_client.get(url)

        assert response.status_code == 200

        extra = response.data[ENUM_EXTRA_KEY]
        assert extra["uuid1"]["description"] == "A person, 30 years old"
        assert extra["uuid2"]["description"] == "Actress and singer, 25 years old"

    def test_duplicate_const_last_row_wins(self, superuser_client, add_view_to_urls):
        """Duplicate enum values keep metadata from the last source row."""

        class DupSourceView(ListAPIView, DynamicSchemaDataMixin):
            permission_classes = ()

            def get_schema_queryset(self):
                raise NotImplementedError

            def get_schema_data(self):
                return [
                    {"id": "same", "name": "First", "bio": "b1"},
                    {"id": "same", "name": "Second", "bio": "b2"},
                ]

        class DupSchemaView(MockDynamicSchemaView):
            source_view = DupSourceView
            default_enum_field = "id"
            default_display_field = "name"
            default_description_field = "bio"

        url_name = add_view_to_urls(DupSchemaView, route="dup-schema", name="dup-schema")
        response = superuser_client.get(reverse(url_name))
        assert response.status_code == 200
        assert response.data["enum"] == ["same"]
        assert response.data[ENUM_EXTRA_KEY]["same"]["display"] == "Second"
        assert response.data[ENUM_EXTRA_KEY]["same"]["description"] == "b2"


class NestedMockSourceView(ListAPIView, DynamicSchemaDataMixin):
    """
    Returns a nested dictionary so we can test `data_path` usage.
    """

    def get_schema_queryset(self):
        # Not used for testing purposes
        raise NotImplementedError

    def get_schema_data(self):
        # Instead of returning a list directly, we nest it under data.inner.items
        return {
            "status": 200,
            "data": {
                "inner": {
                    "items": [
                        {
                            "profile": {
                                "id": "p-uuid1",
                                "name": "Nested John",
                            },
                            "details": {
                                "bio": "Nested Person 1",
                                "language": "en",
                            },
                        },
                        {
                            "profile": {
                                "id": "p-uuid2",
                                "name": "Nested Brigitte",
                            },
                            "details": {
                                "bio": "Nested Person 2",
                                "language": "fr",
                            },
                        },
                    ]
                }
            },
        }


class NestedDynamicSchemaView(MockDynamicSchemaView):
    source_view = NestedMockSourceView

    # We specify which part of the returned data is the *actual* list of items.
    data_path = "data.inner.items"

    # For fields, we’ll reference nested paths like "profile.id", "profile.name", etc.
    default_enum_field = "profile.id"
    default_display_field = "profile.name"
    default_description_field = "details.bio"

    default_enum_extra_fields = {"lang": "details.language"}


@pytest.mark.django_db
class TestDynamicSchemaFromNestedSourceView:

    def test_data_path_and_nested_fields(self, superuser_client, add_view_to_urls):
        """
        Verifies that:
        1. The top-level data is found under `data.inner.items`
        2. Fields with dots (profile.id, profile.name, details.bio, details.language) are correctly resolved.
        """

        url_name = add_view_to_urls(NestedDynamicSchemaView, route="nested-schema", name="nested-schema")
        url = reverse(url_name)
        response = superuser_client.get(url)

        assert response.status_code == 200, response.content

        data = response.data
        assert len(data["enum"]) == 2

        extra = data[ENUM_EXTRA_KEY]
        assert data["enum"][0] == "p-uuid1"
        assert extra["p-uuid1"]["display"] == "Nested John"
        assert extra["p-uuid1"]["description"] == "Nested Person 1"
        assert extra["p-uuid1"]["lang"] == "en"

        assert data["enum"][1] == "p-uuid2"
        assert extra["p-uuid2"]["display"] == "Nested Brigitte"
        assert extra["p-uuid2"]["description"] == "Nested Person 2"
        assert extra["p-uuid2"]["lang"] == "fr"
