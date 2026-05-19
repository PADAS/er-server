import pytest

from django.urls import reverse
from rest_framework.generics import ListAPIView
from rest_framework.request import Request

from schemas.format_serializers import OUTPUT_FORMAT_ONE_OF, output_format_override
from schemas.tests.fixtures import MockDynamicSchemaView, MockSourceView
from schemas.view_mixins import ENUM_EXTRA_KEY, DynamicSchemaDataMixin


@pytest.mark.django_db
class TestDynamicSchemaFromSourceView:

    def test_default_fields(self, superuser_client, add_view_to_urls):
        """
        When no override query params are passed,
        default_value_field and default_label_field should be used.
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

    def test_overridden_fields_with_x_query_params(self, superuser_client, add_view_to_urls):
        """s_value, s_label, s_description, and x_* params override defaults."""
        url_name = add_view_to_urls(MockDynamicSchemaView)
        url = reverse(url_name)
        query_params = {
            "s_value": "custom_id",
            "s_label": "age",
            "s_description": "country",
            "x_icon": "extra_info",
            "x_lang": "language",
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

    def test_s_format_one_of(self, superuser_client, add_view_to_urls):
        url_name = add_view_to_urls(MockDynamicSchemaView)
        response = superuser_client.get(reverse(url_name), {"s_format": "oneOf"})
        assert response.status_code == 200
        data = response.data
        assert "enum" not in data
        assert ENUM_EXTRA_KEY not in data
        assert len(data["oneOf"]) == 2
        first = data["oneOf"][0]
        assert first["const"] == "uuid1"
        assert first["title"] == "John Doe"
        assert first["description"] == "A person"
        assert first["x-info"] == "foobar"

    def test_default_format_class_attribute_without_s_format_query(self, superuser_client, add_view_to_urls):
        """Subclass ``default_format`` is used when ``s_format`` is not in the query string."""

        class OneOfDefaultSchemaView(MockDynamicSchemaView):
            default_format = "oneOf"

        url_name = add_view_to_urls(OneOfDefaultSchemaView, route="oneof-default-schema", name="oneof-default-schema")
        response = superuser_client.get(reverse(url_name))
        assert response.status_code == 200
        data = response.data
        assert "oneOf" in data
        assert "enum" not in data

    def test_unsupported_s_format_returns_400(self, superuser_client, add_view_to_urls):
        """Bad ``s_format`` is user input; should return ``400``, not ``500``."""
        url_name = add_view_to_urls(MockDynamicSchemaView, route="bad-format-schema", name="bad-format-schema")
        response = superuser_client.get(reverse(url_name), {"s_format": "bogus"})
        assert response.status_code == 400
        assert "s_format" in response.data

    def test_output_format_override_pins_format_for_in_process_renders(self, superuser_client, add_view_to_urls, rf):
        """Direct ``generate_dynamic_schema`` calls inside the override produce ``oneOf`` even when
        the view's ``default_format`` is ``enum`` and the request omits ``s_format``."""
        url_name = add_view_to_urls(MockDynamicSchemaView, route="override-schema", name="override-schema")
        url = reverse(url_name)

        view_instance = MockDynamicSchemaView()
        view_instance.kwargs = {}
        drf_request = Request(rf.get(url))

        with output_format_override(OUTPUT_FORMAT_ONE_OF):
            inside_schema = view_instance.generate_dynamic_schema(drf_request)
        outside_schema = view_instance.generate_dynamic_schema(drf_request)

        assert "oneOf" in inside_schema
        assert "enum" not in inside_schema
        assert "enum" in outside_schema
        assert "oneOf" not in outside_schema

    def test_source_view_sees_same_query_params_as_schema_request(self, superuser_client, add_view_to_urls):
        """List source receives the full query string; ``s_`` / ``x_`` do not overlap its filters."""

        captured: dict[str, str] = {}

        class CapturingSourceView(MockSourceView):
            def get_schema_data(self):
                qp = self.request.query_params
                for key in ("category", "s_value", "x_icon"):
                    captured[key] = qp.get(key)
                return super().get_schema_data()

        class CapturingSchemaView(MockDynamicSchemaView):
            source_view = CapturingSourceView

        url_name = add_view_to_urls(CapturingSchemaView, route="capture-schema", name="capture-schema")
        response = superuser_client.get(
            reverse(url_name),
            {"s_value": "id", "x_icon": "extra_info", "category": "animals"},
        )

        assert response.status_code == 200
        assert captured["category"] == "animals"
        assert captured["s_value"] == "id"
        assert captured["x_icon"] == "extra_info"

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

    def test_duplicate_value_field_surfaces_duplicate_enums(self, superuser_client, add_view_to_urls):
        """Same ``s_value`` twice is visible in ``enum``; callers should prefer unique value fields."""

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
            default_value_field = "id"
            default_label_field = "name"
            default_description_field = "bio"

        url_name = add_view_to_urls(DupSchemaView, route="dup-schema", name="dup-schema")
        response = superuser_client.get(reverse(url_name))
        assert response.status_code == 200
        assert response.data["enum"] == ["same", "same"]
        assert response.data[ENUM_EXTRA_KEY]["same"]["display"] == "Second"
        assert response.data[ENUM_EXTRA_KEY]["same"]["description"] == "b2"


class NestedMockSourceView(ListAPIView, DynamicSchemaDataMixin):
    """
    Returns a nested dictionary so we can test `data_path` usage.
    """

    permission_classes = ()

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
    default_value_field = "profile.id"
    default_label_field = "profile.name"
    default_description_field = "details.bio"

    default_extra_fields = {"lang": "details.language"}


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
