import json
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, Type

from django.db.models import QuerySet
from django.http import QueryDict
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.dict_utils import get_nested_value
from utils.drf import sorted_query_parameters_to_string
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer

# JSON Schema extension: per-value metadata for ``enum`` (title, description, and optional extras).
ENUM_EXTRA_KEY = "x-enumExtra"


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

        return list(queryset.values())


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
            "uuid1": {"title": "Feature category 1"},
            "uuid2": {"title": "Feature category 2"}
        }
    }
    ```

    The schema can be customized by setting the following attributes:

    - `schema_title`: The title of the schema.
    - `schema_description`: The description of the schema.

    The fields to describe/build in the schema can be customized by setting the following attributes:

    - `default_const_field`: The default field to use as each entry in ``enum`` (formerly ``const``).
    - `default_title_field`: The default field to use as ``title`` inside ``x-enumExtra``.
    - `default_description_field`: The default field to use as ``description`` inside ``x-enumExtra``.
    - `default_enum_extra_fields`: Optional dict mapping extra keys (e.g. ``icon``) to source field paths.

    And those attributes can be overridden by query parameters in the request:

    - `s_const`: The field to use for ``enum`` values.
    - `s_title`: The field to use as ``title`` in ``x-enumExtra``.
    - `s_description`: The field to use as ``description`` in ``x-enumExtra``.
    - `enum_extra`: JSON object mapping extra keys to source field paths (same shape as ``default_enum_extra_fields``).

    Additionally, the value type can be customized:

    - `default_type`: The default type of value to use in the schema, `string` by default.

    Overridable via query parameter:

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
    default_const_field: str = "id"  # Default value for each ``enum`` entry
    default_title_field: str  # Default value for ``title`` in ``x-enumExtra``
    default_description_field: Optional[str] = None  # Default value for ``description`` in ``x-enumExtra``
    # Map output key -> source field path (dotted), merged into each ``x-enumExtra`` value (e.g. {"icon": "icon_url"}).
    default_enum_extra_fields: Optional[Dict[str, str]] = None

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

    def get_value_field_map(self, request: Request) -> Dict[str, str]:
        """Maps logical roles (const, title, description) to source field paths."""
        query_params = self.get_query_params(request)
        fields_map: Dict[str, str] = {
            "const": query_params.get("s_const", self.default_const_field),
            "title": query_params.get("s_title", self.default_title_field),
        }
        if description_field := query_params.get("s_description", self.default_description_field):
            fields_map["description"] = description_field
        return fields_map

    def get_enum_extra_field_map(self, request: Request) -> Dict[str, str]:
        """
        Maps keys to include under ``x-enumExtra`` entries (beyond title/description) to source field paths.

        Query parameter ``enum_extra`` is a JSON object, same shape as ``default_enum_extra_fields``.
        """
        query_params = self.get_query_params(request)
        raw = query_params.get("enum_extra", self.default_enum_extra_fields)
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ValueError(f"Unable to parse enum_extra: {raw}") from e
            if not isinstance(parsed, dict):
                raise ValueError(f"Invalid enum_extra: {raw}")
            return {str(k): str(v) for k, v in parsed.items()}
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid enum_extra: {raw}")
        return {str(k): str(v) for k, v in raw.items()}

    def resolve_mapped_value(self, item: Dict[str, Any], attr_name: str) -> Any:
        """Resolve a single field path (with optional custom ``get_<first>_from_item``) from a source row."""
        attr_path = attr_name.split(".")
        if field_method := getattr(self, f"get_{attr_path[0]}_from_item", None):
            value = field_method(item)
            if sub_attr_path := ".".join(attr_path[1:]):
                value = get_nested_value(value, sub_attr_path)
        else:
            value = get_nested_value(item, attr_name)
        return value

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
        if not isinstance(data, list):
            data = [data]
        return data

    def get_schema_rows(self, request: Request, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Returns one dict per source row: ``const``, ``title``, optional ``description``, and ``extras`` (dict).
        """
        rows: List[Dict[str, Any]] = []
        value_field_map = self.get_value_field_map(request)
        extra_field_map = self.get_enum_extra_field_map(request)

        for item in data:
            const_val = self.resolve_mapped_value(item, value_field_map["const"])
            title_val = self.resolve_mapped_value(item, value_field_map["title"])
            row: Dict[str, Any] = {"const": const_val, "title": title_val}
            if "description" in value_field_map:
                row["description"] = self.resolve_mapped_value(item, value_field_map["description"])
                if row["description"] is None:
                    row.pop("description")

            extras: Dict[str, Any] = {}
            for out_key, attr_name in extra_field_map.items():
                extras[out_key] = self.resolve_mapped_value(item, attr_name)
            row["extras"] = extras
            rows.append(row)

        return rows

    def build_enum_and_extra(self, rows: List[Dict[str, Any]]) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Collapse rows into ``enum`` and ``x-enumExtra``. Duplicate ``const`` values keep the last row's metadata.
        ``enum`` order follows last occurrence (each value appears once, last position wins).
        """
        ordered = OrderedDict()
        for row in rows:
            const_val = row["const"]
            entry: Dict[str, Any] = {"title": row["title"]}
            if "description" in row:
                entry["description"] = row["description"]
            for k, v in row.get("extras", {}).items():
                entry[k] = v
            if const_val in ordered:
                del ordered[const_val]
            ordered[const_val] = entry
        return list(ordered.keys()), dict(ordered)

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
        schema: Dict[str, Any] = {
            "$id": self.get_schema_id(request),
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": schema_type,
            "title": self.schema_title or "Dynamic schema field",
            "description": self.schema_description or "Dynamic schema description",
        }

        data = self.get_data_from_source_view(request)
        rows = self.get_schema_rows(request, data)
        enum_values, enum_extra = self.build_enum_and_extra(rows)
        schema["enum"] = enum_values
        schema[ENUM_EXTRA_KEY] = enum_extra

        return schema

    def get(self, request: Request, *args, **kwargs) -> Response:
        return Response(self.generate_dynamic_schema(request))
