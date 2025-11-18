from drf_spectacular.utils import inline_serializer

from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError

from observations.views import CustomSchema


class GearsViewSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "lat",
                    "in": "query",
                    "default": 39.7749,
                    "required": True,
                    "description": "Include subjects within a range of 5 nautical miles from this latitude. This value represents the north-south position of a point and is measured in degrees. Latitude ranges from -90.0 to 90.0 are accepted.",
                },
                {
                    "name": "lon",
                    "in": "query",
                    "default": 120.4194,
                    "required": True,
                    "description": "Include subjects within a range of 5 nautical miles from this longitude. This value represents the east-west position of a point and is measured in degrees. Longitude ranges from -180.0 to 180.0 are accepted.",
                },
                {
                    "name": "updated_since",
                    "in": "query",
                    "required": False,
                    "description": "Return Subjects that have been updated since the given timestamp.",
                },
                {
                    "name": "state",
                    "in": "query",
                    "required": False,
                    "description": 'Return Subjects that have the specified state. Use "deployed" for gear in the water, or "hauled" for recovered gear.',
                },
                {
                    "name": "max_nm_range",
                    "in": "query",
                    "required": False,
                    "description": (
                        "Return Subjects that have the specified maximum nautical mile range. "
                        "Must be a positive integer. Negative or non-numeric values will result in a 400 Bad Request. "
                        "Very large values (e.g., >10000) are allowed but may impact performance."
                    ),
                    "schema": {"type": "integer", "minimum": 1, "default": 5, "example": 100},
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation

    def validate_query_params(self, query_params):
        max_nm_range_raw = query_params.get("max_nm_range")
        if max_nm_range_raw is None:
            return None
        try:
            max_nm_range = int(max_nm_range_raw)
        except (TypeError, ValueError):
            raise ValidationError({"max_nm_range": "max_nm_range must be a valid integer."})
        if max_nm_range <= 0:
            raise ValidationError({"max_nm_range": "max_nm_range must be a positive integer."})
        return max_nm_range


gears_list_response_schema = inline_serializer(
    name="GearsListResponse",
    fields={
        "id": drf_serializers.UUIDField(),
        "status": drf_serializers.ChoiceField(
            choices=["deployed", "hauled"], help_text="The deployment status of the gear."
        ),
        "last_updated": drf_serializers.DateTimeField(),
        "display_id": drf_serializers.CharField(),
        "type": drf_serializers.ChoiceField(choices=["trawl", "single"], help_text="The type of the gear."),
        "devices": drf_serializers.ListField(
            child=inline_serializer(
                name="DeviceItem",
                fields={
                    "label": drf_serializers.CharField(),
                    "location": inline_serializer(
                        name="DeviceLocation",
                        fields={"latitude": drf_serializers.FloatField(), "longitude": drf_serializers.FloatField()},
                    ),
                    "device_id": drf_serializers.UUIDField(),
                    "mfr_device_id": drf_serializers.CharField(),
                    "last_updated": drf_serializers.DateTimeField(),
                    "last_deployed": drf_serializers.DateTimeField(),
                },
            ),
            help_text="List of devices associated with the gear.",
        ),
        "manufacturer": drf_serializers.CharField(help_text="The manufacturer of the gear."),
    },
)
