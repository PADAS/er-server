import rest_framework.serializers as serializers
from choices.models import Choice


class ChoiceField(serializers.ChoiceField):
    @property
    def object_choices(self):
        if not self.grouped_choices:
            return {}
        return self.grouped_choices

class ChoiceIconZipSerializer(serializers.Serializer):
    icon = serializers.CharField(max_length=100, allow_null=True)


class ChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    model = serializers.ChoiceField(choices=Choice.MODEL_REF_CHOICES, default=Choice.Field_Reports)
    field = serializers.CharField()
    value = serializers.CharField(allow_blank=True, required=False)
    display = serializers.CharField(allow_blank=True, required=False)
    ordernum = serializers.IntegerField(allow_null=True, required=False)
    icon = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    is_active = serializers.BooleanField(required=False)

    def create(self, validated_data):
        return Choice.objects.create(**validated_data)

    def update(self, instance, validated_data):
        _ = [setattr(instance, field, value) for field, value in validated_data.items()]
        instance.save()
        return instance
