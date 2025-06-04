from rest_framework.generics import ListAPIView

from schemas.view_mixins import DynamicSchemaDataMixin, DynamicSchemaFromSourceView


class MockSourceView(ListAPIView, DynamicSchemaDataMixin):
    """A mock source view to simulate returning data."""

    def get_schema_queryset(self):
        raise NotImplementedError

    def get_schema_data(self):
        return [
            {
                "id": "uuid1",
                "custom_id": "custom_uuid1",
                "name": "John Doe",
                "age": 30,
                "country": "USA",
                "bio": "A person",
                "language": "en",
                "extra_info": "foobar",
            },
            {
                "id": "uuid2",
                "custom_id": "custom_uuid2",
                "name": "Brigitte Bardot",
                "age": 25,
                "country": "France",
                "bio": "Actress and singer",
                "language": "fr",
            },
        ]


class MockDynamicSchemaView(DynamicSchemaFromSourceView):
    """Base test view class for dynamic schema testing."""

    source_view = MockSourceView
    schema_title = "TestSchema"
    schema_description = "Tests data list"
    default_const_field = "id"
    default_title_field = "name"
    default_description_field = "bio"
    default_x_fields = {"info": "extra_info"}
