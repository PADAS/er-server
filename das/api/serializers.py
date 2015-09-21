from observations.models import Subject, Observation
from rest_framework import serializers


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ('id', 'name')


class ObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Observation
        fields = ('id', 'recorded_at', 'additional', 'device')
        id_field = False
        geo_field = 'location'
