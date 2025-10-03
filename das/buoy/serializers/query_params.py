from rest_framework import serializers

from buoy.views.helpers import NAUTICAL_MILE_RADIUS
from observations.utils import check_valid_date_string
from utils.gis import check_valid_lat_lon


class GearsQueryParamsSerializer(serializers.Serializer):
    lat = serializers.FloatField(required=False)
    lon = serializers.FloatField(required=False)
    updated_since = serializers.CharField(required=False)
    state = serializers.ChoiceField(choices=["deployed", "hauled"], required=False, default="deployed")
    max_nm_range = serializers.IntegerField(required=False, default=NAUTICAL_MILE_RADIUS, min_value=1, max_value=1000)
    page = serializers.IntegerField(required=False)
    page_size = serializers.IntegerField(required=False)

    def validate(self, data):
        """Validate query parameters."""
        # Validate updated_since if provided
        if "updated_since" in data:
            try:
                is_valid, parsed_date = check_valid_date_string(data["updated_since"], "updated_since")
            except ValueError:
                raise serializers.ValidationError({"updated_since": "Must be a valid date"})

            if not is_valid:
                raise serializers.ValidationError({"updated_since": "Must be a valid date"})
            data["updated_since"] = parsed_date

        # Validate lat/lon if provided
        lat = data.get("lat")
        lon = data.get("lon")
        if (lat is None) != (lon is None):  # XOR - both should be present or both should be absent
            raise serializers.ValidationError({"lat_lon": "Both lat and lon must be provided together"})

        if lat is not None and lon is not None:
            if not check_valid_lat_lon(latitude=lat, longitude=lon):
                raise serializers.ValidationError(
                    {
                        "lat_lon": "Invalid latitude/longitude values. Latitude must be between -90 and 90, longitude between -180 and 180"
                    }
                )

        return data
