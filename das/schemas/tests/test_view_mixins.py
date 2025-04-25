import json

import pytest

from django.urls import reverse
from rest_framework.generics import ListAPIView

from schemas.tests.fixtures import TestDynamicSchemaView
from schemas.view_mixins import DynamicSchemaDataMixin, DynamicSchemaFromSourceView


@pytest.mark.django_db
class TestDynamicSchemaFromSourceView:

    def test_default_fields(self, superuser_client, add_view_to_urls):
        """
        When no override query params are passed,
        default_const_field and default_title_field should be used.
        """
        url_name = add_view_to_urls(TestDynamicSchemaView)
        url = reverse(url_name)
        response = superuser_client.get(url)

        assert response.status_code == 200

        items = response.data["oneOf"]
        # Expected:
        # const = "uuid1" or "uuid2"
        # title = "John Doe" / "Brigitte Bardot"
        # description = "A person" / "Actress and singer"
        assert items[0]["const"] == "uuid1"
        assert items[0]["title"] == "John Doe"
        assert items[0]["description"] == "A person"
        assert items[1]["const"] == "uuid2"
        assert items[1]["title"] == "Brigitte Bardot"
        assert items[1]["description"] == "Actress and singer"
        # extra_info should appear as x-info by default
        assert items[0]["x-info"] == "foobar"
        # second item has no extra_info, so None is expected
        assert items[1]["x-info"] is None

    def test_overridden_fields(self, superuser_client, add_view_to_urls):
        """
        Test passing s_const, s_title, s_description, and s_x to override defaults.
        """
        url_name = add_view_to_urls(TestDynamicSchemaView)
        url = reverse(url_name)
        query_params = {
            "s_const": "custom_id",
            "s_title": "age",
            "s_description": "country",
            "s_x": json.dumps({"icon": "extra_info", "lang": "language"}),
        }
        response = superuser_client.get(url, query_params)

        assert response.status_code == 200

        items = response.data["oneOf"]
        # Expected:
        # const = "custom_uuid1" or "custom_uuid2"
        # title = 30 / 25
        # description = "USA" / "France"
        assert items[0]["const"] == "custom_uuid1"
        assert items[0]["title"] == 30
        assert items[0]["description"] == "USA"
        assert items[1]["const"] == "custom_uuid2"
        assert items[1]["title"] == 25
        assert items[1]["description"] == "France"
        # extra_info should appear as x-lang and x-icon
        assert items[0]["x-lang"] == "en"
        assert items[0]["x-icon"] == "foobar"
        # second item has no extra_info, so None is expected
        assert items[1]["x-lang"] == "fr"
        assert items[1]["x-icon"] is None

    def test_custom_getter_method(self, superuser_client, add_view_to_urls):
        """
        Test a custom getter method that modifies the bio field.
        """

        class CustomTestDynamicSchemaView(TestDynamicSchemaView):
            """Just adds a custom getter method in the format get_<field_name>_from_item"""

            def get_better_bio_from_item(self, item: dict) -> str:
                return f"{item.get('bio')}, {item.get('age')} years old"

        url_name = add_view_to_urls(CustomTestDynamicSchemaView, route="custom-schema", name="custom-schema")
        url = reverse(url_name)
        response = superuser_client.get(url, {"s_description": "better_bio"})

        assert response.status_code == 200

        items = response.data["oneOf"]
        # Expected:
        # description = "A person, 30 years old" / "Actress and singer, 25 years old"
        assert items[0]["description"] == "A person, 30 years old"
        assert items[1]["description"] == "Actress and singer, 25 years old"

    def test_custom_getter_method_has_precedence(self, superuser_client, add_view_to_urls):
        """
        Test that a custom getter method takes precedence over the default description field.
        """

        class CustomTestDynamicSchemaView(TestDynamicSchemaView):
            def get_bio_from_item(self, item: dict) -> str:
                return f"{item.get('bio')}, {item.get('age')} years old"

        url_name = add_view_to_urls(CustomTestDynamicSchemaView, route="test-schema", name="test-schema")
        url = reverse(url_name)
        response = superuser_client.get(url)

        assert response.status_code == 200

        items = response.data["oneOf"]
        # Expected:
        # description = "A person, 30 years old" / "Actress and singer, 25 years old"
        assert items[0]["description"] == "A person, 30 years old"
        assert items[1]["description"] == "Actress and singer, 25 years old"


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


class NestedTestDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = NestedMockSourceView

    # We specify which part of the returned data is the *actual* list of items.
    data_path = "data.inner.items"

    # For fields, we’ll reference nested paths like "profile.id", "profile.name", etc.
    default_const_field = "profile.id"
    default_title_field = "profile.name"
    default_description_field = "details.bio"

    # Optionally define x-fields
    default_x_fields = {"lang": "details.language"}


@pytest.mark.django_db
class TestDynamicSchemaFromNestedSourceView:

    def test_data_path_and_nested_fields(self, superuser_client, add_view_to_urls):
        """
        Verifies that:
        1. The top-level data is found under `data.inner.items`
        2. Fields with dots (profile.id, profile.name, details.bio, details.language) are correctly resolved.
        """

        url_name = add_view_to_urls(NestedTestDynamicSchemaView, route="nested-schema", name="nested-schema")
        url = reverse(url_name)
        response = superuser_client.get(url)

        assert response.status_code == 200, response.content

        # By default, the view uses schema_mode = "oneOf", so the items should be in `oneOf`.
        items = response.data["oneOf"]
        assert len(items) == 2

        # Check the first item
        assert items[0]["const"] == "p-uuid1"
        assert items[0]["title"] == "Nested John"
        assert items[0]["description"] == "Nested Person 1"
        # We mapped default_x_fields = {"lang": "details.language"}
        assert items[0]["x-lang"] == "en"

        # Check the second item
        assert items[1]["const"] == "p-uuid2"
        assert items[1]["title"] == "Nested Brigitte"
        assert items[1]["description"] == "Nested Person 2"
        assert items[1]["x-lang"] == "fr"
