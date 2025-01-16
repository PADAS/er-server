import json
from typing import Any, Dict, List, Optional, Type

from django.db.models import QuerySet
from django.http import QueryDict
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.dict_utils import get_nested_value
from utils.drf import sorted_query_parameters_to_string
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer


class DynamicSchemaDataMixin:
    """
    A mixin that provides an interface for `DynamicSchemaFromSourceView` to interact with it's  `source_view`,

    Provides methods that can be ovrrided to optimize the queryset, filter data, and avoid unnecessary
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
        "oneOf": [
            {
                "const": "uuid1",
                "title": "Feature category 1"
            },
            {
                "const": "uuid2",
                "title": "Feature category 2"
            }
        ]
    }
    ```

    The schema can be customized by setting the following attributes:

    - `schema_title`: The title of the schema.
    - `schema_description`: The description of the schema.

    The fields to describe/build in the schema can be customized by setting the following attributes:

    - `default_const_field`: The default field to use as `const` in the schema.
    - `default_title_field`: The default field to use as `title` in the schema.
    - `default_description_field`: The default field to use as `description` in the schema.
    - `default_x_fields`: The default fields to use as `x-` in the schema, the expected value is a dictionary.

    And those attributes can be overridden by query parameters in the request:

    - `s_const`: The field to use as `const` in the schema.
    - `s_title`: The field to use as `title` in the schema.
    - `s_description`: The field to use as `description` in the schema.
    - `s_x`: The fields to use as `x-` in the schema, the expected value is a JSON string. (not sure about this one)

    Additionally, the mode and type of the schema can be customized by setting the following attributes:

    - `default_mode`: The schema can be generated in `oneOf`, `anyOf`, `array` or `object` mode.
        - `oneOf`: The field can only have one of the specified values.
        - `anyOf`: The field can have any of the specified values.
        - `array`: The field can have an array of values, where each value must be one of the specified values.
        - `object`: The field can have an object with the specified fields, where each field must be one of the
        specified values.
    - `default_type`: The default type of value to use in the schema, `string` by default.

    Those attributes can be overridden by query parameters in the request:

    - `s_mode`: The mode to use in the schema.
    - `s_type`: The type of value to use in the schema.
    """

    renderer_classes = (DirectJSONRenderer, DirectBrowsableAPIRenderer)

    allowed_methods: List[str] = ("get",)

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
    default_const_field: str = "id"  # Default value for the `const` field
    default_title_field: str  # Default value for the `title` field
    default_description_field: Optional[str] = None  # Default value for the `description` field
    # To define x- attributes, use a dictionary with the key as the x- attribute and the value as the field name.
    # For example: {"icon": "item_icon_field"} will add {"x-icon": "item_icon_field"}
    default_x_fields: Optional[Dict[str, str]] = None

    default_mode = "oneOf"
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
        fields_map = {
            "const": query_params.get("s_const", self.default_const_field),
            "title": query_params.get("s_title", self.default_title_field),
        }
        if description_field := query_params.get("s_description", self.default_description_field):
            fields_map["description"] = description_field

        if x_fields := query_params.get("s_x", self.default_x_fields):
            if isinstance(x_fields, str):
                try:
                    x_fields = json.loads(x_fields)
                except json.JSONDecodeError:
                    raise ValueError(f"Unable to parse x-fields: {x_fields}")
            if not isinstance(x_fields, dict):
                raise ValueError(f"Invalid x-fields: {x_fields}")
            for key, value in x_fields.items():
                fields_map[f"x-{key}"] = value

        return fields_map

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
            data = source_view.get_schema_data()
        else:
            response = source_view.dispatch(original_request)
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

            schema_items.append(schema_item)

        return schema_items

    def get_schema_id(self, request: Request) -> str:
        """
        Returns the schema id, based on the url and the query parameters of the request, in order to help the
        caching of the schema, we will sort the query parameters and append them to the url.
        """
        base_url = request.build_absolute_uri()
        query_params = self.get_query_params(request)
        query_string = sorted_query_parameters_to_string(query_params)

        if not query_params:
            return base_url

        return f"{base_url}?{query_string}"

    def render_schema(self, request: Request) -> Dict[str, Any]:
        """
        Main method to render the schema, it will use the data from the source view to build the schema.
        """
        query_params = self.get_query_params(request)
        schema_mode = query_params.get("s_mode", self.default_mode)
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

        if schema_mode == "anyOf":
            schema["anyOf"] = schema_items
        elif schema_mode in ["oneOf", "array", "object"]:
            # NOTE: "array" and "object" are types, not sure yet of the implementation
            schema["oneOf"] = schema_items

        return schema

    def get(self, request: Request, *args, **kwargs) -> dict:
        return Response(self.render_schema(request))
