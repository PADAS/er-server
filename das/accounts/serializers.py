from django.contrib.auth import get_user_model
import rest_framework.serializers
from rest_framework.exceptions import ValidationError
from core.serializers import ContentTypeField


class UserSerializer(rest_framework.serializers.ModelSerializer):
    role = rest_framework.serializers.CharField(source='get_role')

    class Meta:
        model = get_user_model()
        read_only_fields = ('is_staff', 'is_superuser',
                            'date_joined', 'id', 'is_active')
        fields = ('username', 'email', 'first_name',
                  'last_name', 'role') + read_only_fields


class UserDisplaySerializer(rest_framework.serializers.ModelSerializer):
    content_type = ContentTypeField()

    class Meta:
        model = get_user_model()
        fields = ('username', 'first_name', 'last_name', 'id', 'content_type')
        read_only_fields = fields

    def to_internal_value(self, data):
        if not 'id' in data:
            raise ValidationError('Missing id in deserializing User object')
        obj = get_user_model().objects.get(id=data['id'])
        return obj


def get_user_display(user):
    if not user:
        return ''
    try:
        if user.get_full_name():
            return user.get_full_name()
    except NotImplementedError:
        pass
    return user.get_username()
