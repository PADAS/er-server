from django.contrib.auth import get_user_model
import rest_framework.serializers


class UserSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        read_only_fields = ('is_staff', 'is_superuser',
                            'date_joined', 'id', 'is_active')
        fields = ('username', 'email', 'first_name',
                  'last_name') + read_only_fields


