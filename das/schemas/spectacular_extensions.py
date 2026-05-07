"""
DRF Spectacular extensions for dynamic schema views.

This module provides custom schema introspection for DynamicSchemaFromSourceView
to generate comprehensive OpenAPI documentation including dynamic query parameters.
"""

from typing import Any, Dict, List, Type

from drf_spectacular.extensions import OpenApiViewExtension
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.views import APIView

from das_server.views import CustomSchema
from schemas.view_mixins import ENUM_EXTRA_KEY, DynamicSchemaFromSourceView


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
            parameters = self.build_comprehensive_parameters(source_view_class)
            description = self.build_description(self.target)
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
                            "enum": serializers.ListField(
                                child=serializers.JSONField(),
                                help_text="Allowed values for this field (formerly each item's const)",
                                required=False,
                            ),
                            ENUM_EXTRA_KEY: serializers.JSONField(
                                help_text=(
                                    "Map of enum value -> metadata (title, optional description, "
                                    "and keys from enum_extra / default_enum_extra_fields)"
                                ),
                                required=False,
                            ),
                        },
                        many=False,
                    )
                },
                tags=["Schemas"],
            )(EnhancedDynamicSchemaView)

        return EnhancedDynamicSchemaView

    def build_comprehensive_parameters(self, source_view_class) -> List[OpenApiParameter]:
        """Build comprehensive parameter documentation for dynamic schema endpoint."""
        parameters = []

        # Add schema control parameters
        parameters.extend(self.get_schema_control_parameters())

        # Add source view parameters
        source_params = self.get_source_view_parameters(source_view_class)
        if source_params:
            parameters.extend(source_params)

        return parameters

    def get_schema_control_parameters(self) -> List[OpenApiParameter]:
        """Generate parameters for schema control (s_const, s_title, etc.)."""
        return [
            OpenApiParameter(
                name="s_const",
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Source field path for each value in the top-level ``enum`` list. "
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
                    "Source field path for the ``title`` key inside each ``x-enumExtra`` entry. "
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
                    "Source field path for the ``description`` key inside each ``x-enumExtra`` entry. "
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
                name="s_type",
                location=OpenApiParameter.QUERY,
                required=False,
                description="Type for schema values. Defaults to 'string'.",
                type=OpenApiTypes.STR,
                enum=["string", "number", "boolean", "array", "object"],
                examples=[OpenApiExample(name="type_example", value="string")],
            ),
            OpenApiParameter(
                name="enum_extra",
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "JSON object mapping extra keys to include under each ``x-enumExtra`` entry "
                    "to source field paths (supports dotted paths). "
                    'Example: \'{"icon": "properties.icon_url", "priority": "metadata.level"}\''
                ),
                type=OpenApiTypes.STR,
            ),
        ]

    def get_source_view_parameters(self, source_view_class: Type[APIView]) -> List[OpenApiParameter]:
        """Extract all parameters from the source view (filters, overrides, and decorators)."""
        view_instance = source_view_class()

        # Create minimal request with user for ViewSets that access request.user
        request = HttpRequest()
        request.method = "GET"
        request.user = AnonymousUser()
        request = Request(request)

        # Set up ViewSet action for proper decorator recognition
        if hasattr(view_instance, "action_map"):
            view_instance.action = "list"
            view_instance.action_map = {"get": "list"}

        view_instance.request = request
        view_instance.format_kwarg = None

        auto_schema = CustomSchema()
        auto_schema.view = view_instance
        auto_schema.method = "GET"
        auto_schema.path = "/dummy/"

        # Collect parameters from all sources
        return self.collect_all_parameters(view_instance, auto_schema)

    def collect_all_parameters(self, view_instance, auto_schema) -> List[OpenApiParameter]:
        """
        Collect source view parameters from all common sources: filters, overrides, and decorators.
        Skipping pagination parameters on purpose.
        """
        all_params = []
        parameters = []

        # Get filter parameters (from filterset/filter backends)
        filter_params = auto_schema._get_filter_parameters()
        if filter_params:
            all_params.extend(filter_params)

        # Get @extend_schema_view decorator parameters
        decorator_params = self.extract_decorator_parameters(view_instance)
        if decorator_params:
            all_params.extend(decorator_params)

        for param in all_params:
            if isinstance(param, dict):
                # Convert dict to OpenApiParameter
                parameters.append(
                    OpenApiParameter(
                        name=param["name"],
                        location=OpenApiParameter.QUERY,
                        required=param.get("required", False),
                        description=param.get("description", ""),
                        type=self.convert_schema_to_type(param.get("schema", {})),
                    )
                )
            else:
                # Already an OpenApiParameter object from decorators
                parameters.append(param)

        return parameters

    def extract_decorator_parameters(self, view_instance) -> List[OpenApiParameter]:
        """Extract parameters from @extend_schema_view decorators by inspecting method closures."""
        try:
            # Check common HTTP methods for @extend_schema_view decorators
            for method_name in ["list", "get", "post", "put", "patch", "delete"]:
                params = self.extract_from_method(view_instance.__class__, method_name)
                if params:
                    return params
            return []
        except Exception:
            return []

    def extract_from_method(self, view_class, method_name: str) -> List[OpenApiParameter]:
        """Extract decorator parameters from a specific method."""
        if not hasattr(view_class, method_name):
            return []

        method = getattr(view_class, method_name)

        # Check if method has @extend_schema_view decorator
        if not (hasattr(method, "kwargs") and "schema" in method.kwargs):
            return []

        extended_schema_class = method.kwargs["schema"]
        return self.extract_from_schema_closure(extended_schema_class)

    def extract_from_schema_closure(self, extended_schema_class) -> List[OpenApiParameter]:
        """Extract parameters from ExtendedSchema closure variables."""
        if not hasattr(extended_schema_class, "get_override_parameters"):
            return []

        override_method = extended_schema_class.get_override_parameters

        # Parameters are stored in closure variables
        if not (hasattr(override_method, "__closure__") and override_method.__closure__):
            return []

        parameters = []
        for cell in override_method.__closure__:
            content = cell.cell_contents
            # Look for lists of OpenApiParameter objects
            if isinstance(content, (list, tuple)):
                for item in content:
                    if hasattr(item, "name") and hasattr(item, "description"):
                        parameters.append(item)

        return parameters

    def convert_schema_to_type(self, schema: Dict[str, Any]) -> OpenApiTypes:
        """Convert schema type to OpenApiTypes enum."""
        schema_type = schema.get("type", "string")
        type_mapping = {
            "string": OpenApiTypes.STR,
            "integer": OpenApiTypes.INT,
            "number": OpenApiTypes.NUMBER,
            "boolean": OpenApiTypes.BOOL,
            "array": OpenApiTypes.STR,
            "object": OpenApiTypes.OBJECT,
        }
        return type_mapping.get(schema_type, OpenApiTypes.STR)

    def get_field_path_examples(self, source_view_class: Type[APIView]) -> Dict[str, List[str]]:
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

    def build_source_parameters_section(self, source_view_class) -> str:
        """Build the source parameters section showing discovered parameters."""
        if not source_view_class:
            return "2. **Source View Parameters**: None available"

        source_name = source_view_class.__name__
        source_params = self.get_source_view_parameters(source_view_class)

        if not source_params:
            return f"2. **Source View Parameters**: No parameters discovered from {source_name}"

        # Format parameters for documentation
        param_lines = [self.format_parameter_line(param) for param in source_params]
        param_list = "\n".join(param_lines) if param_lines else "   - None discovered"

        return f"""2. **Source View Parameters**: Parameters from {source_name} \n {param_list}"""

    def format_parameter_line(self, param) -> str:
        """Format a single parameter for documentation display."""
        # Extract parameter info regardless of type (OpenApiParameter or dict)
        if hasattr(param, "name"):
            name = param.name
            description = getattr(param, "description", "")
            required = getattr(param, "required", False)
        elif isinstance(param, dict):
            name = param.get("name", "unknown")
            description = param.get("description", "")
            required = param.get("required", False)
        else:
            return "   - Unknown parameter type"

        req_text = " (required)" if required else ""
        desc_text = f": {description}" if description else ""
        return f"   - `{name}`{req_text}{desc_text}"

    def build_nested_fields_section(self, source_view_class) -> str:
        """Build the nested fields section showing discovered nested fields."""
        if not source_view_class:
            return "3. **Available Fields**: None available"

        source_name = source_view_class.__name__
        field_examples = self.get_field_path_examples(source_view_class)

        if not field_examples:
            return f"3. **Available Fields**: No fields discovered from {source_name}"

        fields_section = ""
        # Format nested fields for documentation
        for field_type, fields in field_examples.items():
            if not fields:
                continue
            fields = [f"`{field}`" for field in fields]
            fields_section += f"   - {field_type.replace('_', ' ').capitalize()}: {', '.join(fields)}\n"

        return f"""3. **Available Fields**: Available fields from {source_name} \n {fields_section}"""

    def build_description(self, view_class) -> str:
        """Generate a comprehensive description for the endpoint."""
        base_description = getattr(view_class, "schema_description", "Dynamic schema endpoint")
        source_view_name = getattr(view_class, "source_view", None)
        source_name = source_view_name.__name__ if source_view_name else "unknown"

        # Get discovered source view parameters
        source_params_section = self.build_source_parameters_section(source_view_name)
        nested_fields_section = self.build_nested_fields_section(source_view_name)

        return f"""{base_description}

This endpoint dynamically generates JSON schemas based on data from {source_name}.

**Query Parameter Categories:**

1. **Schema Control Parameters** (s_* and related): Control how the schema is generated
   - `s_const`: Field to use for each ``enum`` value (supports dotted paths)
   - `s_title`: Field to use for ``title`` inside ``x-enumExtra`` (supports dotted paths)
   - `s_description`: Field to use for ``description`` inside ``x-enumExtra`` (supports dotted paths)
   - `enum_extra`: JSON object mapping extra keys to source field paths (merged into ``x-enumExtra`` entries)
   - `s_type`: JSON Schema ``type`` for the field

{source_params_section}
{nested_fields_section}

**Example Usage:**
- Basic: `?s_title=name&s_const=id`
- Nested: `?s_title=properties.display_name&s_description=metadata.summary`
- Extra metadata: `?enum_extra={{"icon": "properties.icon_url", "priority": "metadata.level"}}`"""
