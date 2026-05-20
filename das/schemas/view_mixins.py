import json
from typing import Any, Dict, List, Optional, Type

from django.db.models import QuerySet
from django.http import QueryDict
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from schemas.format_serializers import (
    ENUM_EXTRA_KEY,
    OUTPUT_FORMAT_ENUM,
    OUTPUT_FORMATS,
    apply_output_format,
    get_output_format_override,
)
from utils.dict_utils import get_nested_value
from utils.drf import sorted_query_parameters_to_string
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer

# Re-export for existing importers (e.g. ``spectacular_extensions``, tests).
__all__ = ["ENUM_EXTRA_KEY", "DynamicSchemaDataMixin", "DynamicSchemaFromSourceView"]


class DynamicSchemaDataMixin:
    """
    A mixin that provides an interface for `DynamicSchemaFromSourceView` to interact with it's  `source_view`,

    Provides methods that can be overriden to optimize the queryset, filter data, and avoid unnecessary
    serialization/de-serialization.
    """

    def get_schema_queryset(self) -> QuerySet:
        """Override this method to customize the queryset used to build schemas"""
        assert hasattr(
            self, "get_queryset"
        ), "You must implement a `get_queryset` method or override `get_schema_queryset`"
        return self.get_queryset()

    def get_schema_data(self) -> List[Dict[str, Any]]:
        """
        This is the main method to get the data to build the schema, it will use the queryset from
        `get_schema_queryset`, the default implementation will imitate the logic of
        `ListAPIView.list()` but without pagination.
        """
        queryset = self.get_schema_queryset()

        if hasattr(self, "filter_queryset"):
            queryset = self.filter_queryset(queryset)
        if hasattr(self, "optimize_queryset"):
            queryset = self.optimize_queryset(queryset)
        if hasattr(self, "get_serializer"):
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        return queryset.values()


class DynamicSchemaFromSourceView(APIView):
    """
    A view that "dinamically" generates a JSON schema based on data from an existing view as source
    (that must be a subclass of `rest_framework.views.APIView`).

    An example result would be something like:

    ```json
    {
        "$id": "a unique url based on the request url and query parameters",
        "$schema": "draft/2020-12/schema",

        "title": "FeatureCategories",
        "description": "A list of all feature categories available to the client",
        "type": "string",
        "enum": ["uuid1", "uuid2"],
        "x-enumExtra": {
            "uuid1": {"display": "Feature category 1"},
            "uuid2": {"display": "Feature category 2"}
        }
    }
    ```

    The schema can be customized by setting the following attributes:

    - `schema_title`: The title of the schema.
    - `schema_description`: The description of the schema.

    The fields to describe/build in the schema can be customized by setting the following attributes:

    - `default_value_field`: The default field to use as `value` / `const` in the schema.
    - `default_label_field`: The default field to use as `display` / `title` in the schema.
    - `default_description_field`: The default field to use as `description` in the schema.
    - `default_extra_fields`: The default fields to use as `x-` extras, the expected value is a dictionary.

    And those attributes can be overridden by query parameters in the request:

    - `s_value`: The field to use as `value` / `const` in the schema.
    - `s_label`: The field to use as `display` / `title` in the schema.
    - `s_description`: The field to use as `description` in the schema.
    - `x_<name>`: Per-option extra metadata, e.g. `x_icon=icon_url` maps source `icon_url` to key `icon`.

    Additionally, the format and type of the schema can be customized by setting the following attributes:

    - `default_format`: Output shape, `enum` (with `x-enumExtra`, default) or `oneOf`.
    - `default_type`: The default type of value to use in the schema, `string` by default.

    Those attributes can be overridden by query parameters in the request:

    - `s_format`: The output format to use in the schema (`enum` or `oneOf`).
    - `s_type`: The type of value to use in the schema.
    """

    renderer_classes = (DirectJSONRenderer, DirectBrowsableAPIRenderer)

    allowed_methods: List[str] = ("GET",)

    source_view: Type[APIView]  # The source view to get the data from
    source_view_initkwargs: dict  # Extra kwargs to pass to the source view

    # In case we are using the complete response of the view, then this `path` can be used to traverse the data
    # structure and reach the list of items to use as source data.
    # For example if the response is dictionary like {"data": [{"id": "uuid1", "name": "Feature category 1"}, ...]}
    # then the path would be "data".
    data_path: Optional[str] = None

    # Query parameters to ignore when building the schema id and the schema items, at the moment we are ignoring
    # pagination parameters.
    ignored_query_params = ("page", "page_size", "offset", "limit")

    # The fields to describe/build the schema
    schema_title: Optional[str] = None
    schema_description: Optional[str] = None

    # Default fields to build the list of items
    default_value_field: str = "id"  # Default source field for `value` / `const`
    default_label_field: str = "name"  # Default source field for `display` / `title`
    default_description_field: Optional[str] = None  # Default source field for `description`
    # To define x- attributes, use a dictionary with the key as the x- attribute and the value as the field name.
    # For example: {"icon": "item_icon_field"} maps source `item_icon_field` to key `icon`.
    default_extra_fields: Optional[Dict[str, str]] = None

    default_format: str = OUTPUT_FORMAT_ENUM
    default_type = "string"

    def get_source_view(self, request: Request) -> Type[APIView]:
        if getattr(self, "source_view", None):
            return self.source_view
        raise NotImplementedError("`source_view` must be defined or `get_source_view` must be implemented")

    def get_source_view_initkwargs(self, request: Request) -> dict:
        return getattr(self, "source_view_initkwargs", {})

    def instantiate_source_view(self, request: Request, **kwargs) -> APIView:
        """
        Instantiates a view class, pass the request and the specified kwargs
        """
        source_view_class = self.get_source_view(request)
        kwargs.update(self.get_source_view_initkwargs(request))
        source_view_instance = source_view_class(**kwargs)
        source_view_instance.args = getattr(self, "args", ())
        source_view_instance.kwargs = kwargs

        return source_view_instance

    def get_query_params(self, request: Request) -> QueryDict:
        """
        Filters ignored query parameters, for the schema view.
        """
        query_params = request.query_params.copy()
        for key in list(query_params.keys()):
            if key in self.ignored_query_params:
                query_params.pop(key)
        return query_params

    def get_fields_map(self, request: Request) -> Dict[str, str]:
        """
        Builds a map of the fields to render in the schema, based on default fields and query parameters.
        """
        query_params = self.get_query_params(request)
        fields_map: Dict[str, str] = {}
        if self.default_extra_fields:
            fields_map.update(self.default_extra_fields)
        for key in query_params:
            if key.startswith("x_") and len(key) > 2 and (path := query_params.get(key)) is not None:
                fields_map[key[2:]] = path
        fields_map["value"] = query_params.get("s_value") or self.default_value_field
        fields_map["label"] = query_params.get("s_label") or self.default_label_field
        if description_field := query_params.get("s_description") or self.default_description_field:
            fields_map["description"] = description_field
        return fields_map

    def get_output_format(self, request: Request) -> str:
        """
        Resolves the output shape: an active ``output_format_override`` wins; otherwise ``s_format`` /
        ``default_format``. Internal callers (e.g. alerting) use ``output_format_override`` to pin a
        single shape regardless of the request.
        """
        if override := get_output_format_override():
            return override
        query_params = self.get_query_params(request)
        output_format = query_params.get("s_format") or self.default_format
        if output_format not in OUTPUT_FORMATS:
            raise ValidationError(
                {"s_format": f"Unsupported value: {output_format!r}. Allowed: {', '.join(sorted(OUTPUT_FORMATS))}."}
            )
        return output_format

    def get_data_from_source_view(self, request: Request) -> List[Dict[str, Any]]:
        """
        Main method that uses source view and gets the data to build the schema.
        If the view does not have a 'get_schema_data' method, it will call the view and get the data from the response.
        """

        source_view = self.instantiate_source_view(request)
        original_request = request._request
        original_request.GET = self.get_query_params(request)

        if hasattr(source_view, "get_schema_data"):
            source_view.request = request
            source_view.format_kwarg = source_view.get_format_suffix()
            source_view.check_permissions(request)
            data = source_view.get_schema_data()

        else:

            def handle_exception(exc):
                raise exc

            source_view.handle_exception = handle_exception
            response = source_view.dispatch(original_request, *source_view.args, **source_view.kwargs)

            if hasattr(response, "render"):
                response.render()
                data = response.data
            else:
                content = response.content
                try:
                    data = json.loads(content)
                except (ValueError, json.JSONDecodeError) as e:
                    raise ValueError(f"Unable to parse response content: {content}") from e

        if self.data_path:
            data = get_nested_value(data, self.data_path)
            if data is None:
                raise ValueError(f"Unable to find data at path: {self.data_path or 'root'}")
        return data

    def get_schema_items(self, request: Request, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Returns the items for the schema, based on the data from the source view. Also, it will use the fields map
        to map the fields from the source view to the schema fields.
        It's possible to define custom methods to get the values from the source view, by defining a method
        `get_{field_name}_from_item` in this view.
        """
        schema_items = []
        fields_map = self.get_fields_map(request)

        for item in data:
            schema_item = {}
            for key, attr_name in fields_map.items():
                attr_path = attr_name.split(".")

                if field_method := getattr(self, f"get_{attr_path[0]}_from_item", None):
                    value = field_method(item)
                    if sub_attr_path := ".".join(attr_path[1:]):
                        value = get_nested_value(value, sub_attr_path)
                else:
                    value = get_nested_value(item, attr_name)
                schema_item[key] = value

            # Omit description when unresolved so clients do not see JSON null in oneOf entries.
            if schema_item.get("description") is None:
                schema_item.pop("description", None)

            schema_items.append(schema_item)

        return schema_items

    def get_schema_id(self, request: Request) -> str:
        """
        Returns the schema id, based on the url and the query parameters of the request, in order to help the
        caching of the schema, we will sort the query parameters and append them to the url.
        """
        query_params = self.get_query_params(request)
        query_string = sorted_query_parameters_to_string(query_params)

        if not query_params:
            return request.build_absolute_uri()

        base_url = request.build_absolute_uri(request.path)
        return f"{base_url}?{query_string}"

    def generate_dynamic_schema(self, request: Request) -> Dict[str, Any]:
        """
        Generates a dict with a JSON schema format, using the specified source view.
        """
        query_params = self.get_query_params(request)
        schema_type = query_params.get("s_type", self.default_type)
        schema = {
            "$id": self.get_schema_id(request),
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": schema_type,
            "title": self.schema_title or "Dynamic schema field",
            "description": self.schema_description or "Dynamic schema description",
        }

        data = self.get_data_from_source_view(request)
        if not isinstance(data, list):
            data = [data]

        schema_items = self.get_schema_items(request, data)
        apply_output_format(schema, schema_items, self.get_output_format(request))

        return schema

    def get(self, request: Request, *args, **kwargs) -> Response:
        return Response(self.generate_dynamic_schema(request))
