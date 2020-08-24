from rest_framework import serializers


class BaseSerializer(serializers.Serializer):
    """This serves as the base class from which all other serializers extend.

    It contains fields common to all API resources in the app.
    """

    id = serializers.CharField(read_only=True)

    def __init__(self, excludes=list(), *args, **kwargs):
        super().__init__(*args, **kwargs)

        map(
            lambda x: setattr(self, x, None),
            excludes
        )


class TimestampMixin(serializers.Serializer):
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
