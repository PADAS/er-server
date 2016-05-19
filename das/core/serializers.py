import rest_framework.serializers as serializers
from django.contrib.contenttypes.models import ContentType


class ContentTypeField(serializers.Field):
    def to_representation(self, value):
        return value._meta.label_lower

    def to_internal_value(self, data):
        app_label, model = data.split('.')
        return ContentType.objects.get(app_label=app_label, model=model)

    def get_attribute(self, obj):
        # We pass the object instance onto `to_representation`,
        # not just the field attribute.
        return obj

    def get_value(self, dictionary):
        return dictionary[self.field_name]
