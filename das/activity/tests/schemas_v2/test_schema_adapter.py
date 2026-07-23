import json

import pytest

from activity.schemas.schema_adapter import (
    SchemaAdapterFactory,
    V1SchemaAdapter,
    V2SchemaAdapter,
)
from factories import ChoiceFactory

V1_SCHEMA = {
    "schema": {"type": "object", "properties": {}},
    "definition": [],
}
V2_SCHEMA = {
    "json": {"type": "object", "properties": {}},
    "ui": {},
}


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestSchemaAdapterFactory:
    @pytest.mark.parametrize("schema", [V1_SCHEMA, json.dumps(V1_SCHEMA)])
    def test_creates_v1_adapter_for_v1_schema(self, schema):
        adapter = SchemaAdapterFactory.create_adapter(schema)

        assert isinstance(adapter, V1SchemaAdapter)

    @pytest.mark.parametrize("schema", [V2_SCHEMA, json.dumps(V2_SCHEMA)])
    def test_creates_v2_adapter_for_v2_schema(self, schema):
        adapter = SchemaAdapterFactory.create_adapter(schema)

        assert isinstance(adapter, V2SchemaAdapter)

    def test_creates_v1_adapter_for_unrendered_template_schema(self):
        ChoiceFactory.create(model="activity.event", field="status", value="active", display="Active")
        schema = """
        {
            "schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": {{enum___status___values}},
                        "enumNames": {{enum___status___names}}
                    }
                }
            },
            "definition": []
        }
        """

        adapter = SchemaAdapterFactory.create_adapter(schema)

        assert isinstance(adapter, V1SchemaAdapter)
        assert adapter.rendered_schema["schema"]["properties"]["status"]["enum"] == ["active"]

    def test_raises_for_malformed_json_string(self):
        with pytest.raises(json.JSONDecodeError):
            SchemaAdapterFactory.create_adapter("not valid json")

    def test_rejects_json_that_does_not_decode_to_an_object(self):
        with pytest.raises(ValueError, match="schema JSON must decode to an object"):
            SchemaAdapterFactory.create_adapter("[]")

    def test_defaults_unknown_dictionary_shape_to_v2(self):
        adapter = SchemaAdapterFactory.create_adapter({"unknown": "shape"})

        assert isinstance(adapter, V2SchemaAdapter)

    def test_rejects_unsupported_schema_input(self):
        with pytest.raises(TypeError, match="schema must be a string or dictionary"):
            SchemaAdapterFactory.create_adapter(42)
