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
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation
