from sensors.models import Subject, Observation
from rest_framework import serializers
import rest_framework_gis.serializers as gis_serializers


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ('id', 'name')


class ObservationSerializer(gis_serializers.GeoFeatureModelSerializer):
    class Meta:
        model = Observation
        fields = ('id', 'recorded_at', 'additional', 'device')
        id_field = False
        geo_field = 'location'
