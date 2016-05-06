import rest_framework.serializers


class ReadOnlyJSONField(rest_framework.serializers.ReadOnlyField):
    def to_native(self, obj):
        return obj


class PointField(rest_framework.serializers.ReadOnlyField):
    def to_native(self, obj):
        return obj

    def to_representation(self, value):
        return dict(lon=value.x, lat=value.y)


class SourceObservationSerializer(rest_framework.serializers.ModelSerializer):
    id = rest_framework.serializers.UUIDField()
    recorded_at = rest_framework.serializers.DateTimeField(label='recorded at') # fix time
    created_at = rest_framework.serializers.DateTimeField(label='created at')
    location = PointField(label='location')
    additional = rest_framework.serializers.DictField(label='additional')
