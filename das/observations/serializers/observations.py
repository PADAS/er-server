from rest_framework import serializers
from rest_framework.fields import DateTimeField

from observations.models import Observation


class FlattenObservationSerializer(serializers.ModelSerializer):
    coordinates = serializers.SerializerMethodField()
    time = DateTimeField(source="recorded_at")

    class Meta:
        model = Observation
        fields = ("coordinates", "time")

    def get_coordinates(self, obj):
        longitude = float(obj.location.x)
        latitude = float(obj.location.y)
        return [longitude, latitude]
