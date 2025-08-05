"""
DRF Spectacular extensions for dynamic schema views.

This module provides custom schema introspection for DynamicSchemaFromSourceView
to generate comprehensive OpenAPI documentation including dynamic query parameters.
"""

from typing import Any, Dict, List, Type

from drf_spectacular.extensions import OpenApiViewExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)

from django.http import HttpRequest
from rest_framework import serializers
from rest_framework.views import APIView

from schemas.view_mixins import DynamicSchemaFromSourceView


class DynamicSchemaViewExtension(OpenApiViewExtension):
    """
    Custom OpenAPI extension for DynamicSchemaFromSourceView subclasses.

    Generates comprehensive documentation for dynamic query parameters including:
    - Schema control parameters (s_const, s_title, etc.)
    - Source view parameters
    - Available field paths for nested property access
    """

    target_class = DynamicSchemaFromSourceView
    match_subclasses = True

    def view_replacement(self):
        """Replace the view's schema generation with our custom implementation."""

        class EnhancedDynamicSchemaView(self.target):
            serializer_class = None  # Fix "unable to guess serializer" error

            @classmethod
            def get_extra_actions(cls):
                return []  # Not a ViewSet with actions

        source_view_class = getattr(self.target, "source_view", None)
        if source_view_class:
            parameters = self._build_comprehensive_parameters(source_view_class)
            description = self._build_description(self.target)
            summary = f"Dynamic {getattr(self.target, 'schema_title', 'Schema')}"

            EnhancedDynamicSchemaView = extend_schema(
                summary=summary,
                description=description,
                parameters=parameters,
                responses={
                    200: inline_serializer(
                        name=f"{self.target.__name__}Response",
                        fields={
                            "$id": serializers.URLField(help_text="Schema identifier with applied query parameters"),
                            "$schema": serializers.URLField(
                                help_text="Meta-schema version (Draft 2020-12)",
                                default="https://json-schema.org/draft/2020-12/schema",
                            ),
                            "type": serializers.ChoiceField(
                                choices=["string", "array", "object"],
                                help_text="JSON Schema type based on s_type parameter",
                            ),
                            "title": serializers.CharField(help_text="Human-readable schema title"),
                            "description": serializers.CharField(help_text="Schema description", required=False),
                            "oneOf": serializers.ListField(
                                child=inline_serializer(
                                    name=f"{self.target.__name__}Choice",
                                    fields={
                                        "const": serializers.JSONField(
                                            help_text="Choice value (ID, name, or other identifier)"
                                        ),
                                        "title": serializers.CharField(help_text="Human-readable choice label"),
                                        "description": serializers.CharField(
                                            help_text="Choice description", required=False
                                        ),
                                    },
                                ),
                                help_text="Available choices when s_mode=oneOf",
                                required=False,
                            ),
                        },
                        many=False,
                    )
                },
                tags=["Schemas"],
            )(EnhancedDynamicSchemaView)

        return EnhancedDynamicSchemaView

    def _build_comprehensive_parameters(self, source_view_class) -> List[OpenApiParameter]:
        """Build comprehensive parameter documentation for dynamic schema endpoint."""
        parameters = []

        # Add schema control parameters
        parameters.extend(self._get_schema_control_parameters())

        # Add source view parameters
        source_params = self._get_source_view_parameters(source_view_class)
        if source_params:
            parameters.extend(source_params)

        # Add field documentation
        field_examples = self._get_field_path_examples(source_view_class)
        if field_examples:
            parameters.extend(self._generate_field_documentation(field_examples))

        return parameters

    def _get_schema_control_parameters(self) -> List[OpenApiParameter]:
        """Generate parameters for schema control (s_const, s_title, etc.)."""
        return [
            OpenApiParameter(
                name="s_const",
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Field to use as 'const' value in schema items. "
                    f"Defaults to '{getattr(self.target, 'default_const_field', 'id')}'. "
                    "Supports dotted paths for nested properties (e.g., 'properties.name')."
                ),
                type=OpenApiTypes.STR,
                examples=[
                    OpenApiExample(name="direct_field", summary="Direct field access", value="id"),
                    OpenApiExample(name="nested_property", summary="Nested property access", value="properties.name"),
                ],
            ),
            OpenApiParameter(
                name="s_title",
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Field to use as 'title' value in schema items. "
                    f"Defaults to '{getattr(self.target, 'default_title_field', 'name')}'. "
                    "Supports dotted paths for nested properties."
                ),
                type=OpenApiTypes.STR,
                examples=[
                    OpenApiExample(name="name_field", summary="Name field", value="name"),
                    OpenApiExample(name="nested_title", summary="Nested title access", value="metadata.title"),
                ],
            ),
            OpenApiParameter(
                name="s_description",
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Field to use as 'description' value in schema items. "
                    f"Defaults to '{getattr(self.target, 'default_description_field', 'None')}'. "
                    "Supports dotted paths for nested properties."
                ),
                type=OpenApiTypes.STR,
                examples=[
                    OpenApiExample(name="description_field", summary="Description field", value="description"),
                    OpenApiExample(
                        name="nested_desc", summary="Nested description access", value="metadata.description"
                    ),
                ],
            ),
            OpenApiParameter(
                name="s_mode",
                location=OpenApiParameter.QUERY,
                required=False,
                description="Schema composition mode for the generated schema. Defaults to 'oneOf'.",
                type=OpenApiTypes.STR,
                enum=["oneOf", "anyOf", "array", "object"],
                examples=[OpenApiExample(name="mode_example", summary="Schema mode", value="oneOf")],
            ),
            OpenApiParameter(
                name="s_type",
                location=OpenApiParameter.QUERY,
                required=False,
                description="Type for schema values. Defaults to 'string'.",
                type=OpenApiTypes.STR,
                enum=["string", "integer", "number", "boolean", "array", "object"],
                examples=[OpenApiExample(name="type_example", summary="Schema value type", value="string")],
            ),
            OpenApiParameter(
                name="s_x",
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "JSON object defining custom x- extensions for schema items. "
                    "Keys become x- prefixed properties, values are field paths. "
                    'Example: \'{"icon": "properties.icon_url", "color": "metadata.color"}\''
                ),
                type=OpenApiTypes.STR,
                examples=[
                    OpenApiExample(
                        name="custom_extensions",
                        summary="Custom x- extensions",
                        value='{"icon": "properties.icon_url", "color": "metadata.color"}',
                    )
                ],
            ),
        ]

    def _get_source_view_parameters(self, source_view_class: Type[APIView]) -> List[OpenApiParameter]:
        """Extract parameters from the source view using DRF Spectacular introspection."""
        try:
            # Create a dummy view instance with request
            view_instance = source_view_class()

            # Create minimal request object for introspection
            request = HttpRequest()
            request.method = "GET"
            view_instance.request = request
            view_instance.format_kwarg = None

            # Use AutoSchema to extract parameters
            auto_schema = AutoSchema()
            auto_schema.view = view_instance
            auto_schema.method = "GET"
            auto_schema.path = "/dummy/"

            parameters = []

            # Get filter parameters
            filter_params = auto_schema._get_filter_parameters()
            if filter_params:
                for param in filter_params:
                    if isinstance(param, dict):
                        parameters.append(
                            OpenApiParameter(
                                name=param["name"],
                                location=OpenApiParameter.QUERY,
                                required=param.get("required", False),
                                description=param.get("description", ""),
                                type=self._convert_schema_to_type(param.get("schema", {})),
                            )
                        )
                    else:
                        parameters.append(param)
            return parameters

        except Exception:
            # If introspection fails, return empty list
            return []

    def _convert_schema_to_type(self, schema: Dict[str, Any]) -> OpenApiTypes:
        """Convert schema type to OpenApiTypes enum."""
        schema_type = schema.get("type", "string")
        type_mapping = {
            "string": OpenApiTypes.STR,
            "integer": OpenApiTypes.INT,
            "number": OpenApiTypes.NUMBER,
            "boolean": OpenApiTypes.BOOL,
            "array": OpenApiTypes.OBJECT,  # Default fallback
            "object": OpenApiTypes.OBJECT,
        }
        return type_mapping.get(schema_type, OpenApiTypes.STR)

    def _get_field_path_examples(self, source_view_class: Type[APIView]) -> Dict[str, List[str]]:
        """Generate examples of available field paths from the source view's serializer."""
        try:
            view_instance = source_view_class()
            serializer_class = getattr(view_instance, "serializer_class", None)

            if not serializer_class:
                return {}

            # Get field information from serializer
            serializer = serializer_class()
            field_examples = {"direct_fields": [], "nested_fields": [], "related_fields": []}

            for field_name, field in serializer.fields.items():
                field_examples["direct_fields"].append(field_name)

                # Add nested examples for related fields
                if isinstance(field, serializers.RelatedField):
                    field_examples["related_fields"].append(f"{field_name}.id")
                    field_examples["related_fields"].append(f"{field_name}.name")

                # Add common nested patterns
                if field_name in ["properties", "metadata", "additional"]:
                    field_examples["nested_fields"].append(f"{field_name}.name")
                    field_examples["nested_fields"].append(f"{field_name}.description")

            return field_examples

        except Exception:
            return {}

    def _generate_field_documentation(self, field_examples: Dict[str, List[str]]) -> List[OpenApiParameter]:
        """Generate documentation for available field paths."""
        available_fields = []
        available_fields.extend(field_examples.get("direct_fields", []))
        available_fields.extend(field_examples.get("nested_fields", []))
        available_fields.extend(field_examples.get("related_fields", []))

        if not available_fields:
            return []

        return [
            OpenApiParameter(
                name="_available_fields",
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "This parameter is for documentation only. "
                    "Available field paths for s_const, s_title, s_description: "
                    f"{', '.join(sorted(set(available_fields[:20])))} "
                    f"{'...' if len(available_fields) > 20 else ''}"
                ),
                type=OpenApiTypes.STR,
                deprecated=True,
            )
        ]

    def _build_description(self, view_class) -> str:
        """Generate a comprehensive description for the endpoint."""
        base_description = getattr(view_class, "schema_description", "Dynamic schema endpoint")
        source_view_name = getattr(view_class, "source_view", None)
        source_name = source_view_name.__name__ if source_view_name else "unknown"

        return f"""{base_description}

This endpoint dynamically generates JSON schemas based on data from {source_name}.

**Query Parameter Categories:**

1. **Schema Control Parameters** (s_*): Control how the schema is generated
   - `s_const`: Field to use for 'const' values (supports dotted paths)
   - `s_title`: Field to use for 'title' values (supports dotted paths)
   - `s_description`: Field to use for 'description' values (supports dotted paths)
   - `s_x`: JSON object for custom x- extensions
   - `s_mode`: Schema composition mode (oneOf, anyOf, etc.)
   - `s_type`: Value type for schema items

2. **Source View Parameters**: Any parameters accepted by the underlying {source_name}

3. **Nested Field Access**: Use dotted notation to access nested properties:
   - Direct fields: `name`, `id`, `value`
   - Nested properties: `properties.name`, `metadata.description`
   - Related fields: `category.name`, `user.display_name`

**Example Usage:**
- Basic: `?s_title=name&s_const=id`
- Nested: `?s_title=properties.display_name&s_description=metadata.summary`
- Custom: `?s_x={{"icon": "properties.icon_url", "priority": "metadata.level"}}`"""
