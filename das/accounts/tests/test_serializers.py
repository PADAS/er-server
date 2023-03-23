import pytest

from accounts.serializers import UserSerializer


@pytest.mark.django_db
class TestUserSerializer:
    def test_serialized_user(self, ops_user):
        ops_user.username = "username"
        ops_user.first_name = "Antonio"
        ops_user.last_name = "Banderas"
        ops_user.pin = "9876"
        ops_user.is_staff = False
        ops_user.is_superuser = False
        ops_user.additional = {"role": "Super DevOps"}
        ops_user.save()

        serialized_user = UserSerializer(ops_user).data

        assert serialized_user["id"] == str(ops_user.id)
        assert serialized_user["username"] == ops_user.username
        assert serialized_user["first_name"] == ops_user.first_name
        assert serialized_user["last_name"] == ops_user.last_name
        assert serialized_user["role"] == ops_user.additional["role"]
        assert serialized_user["pin"] == ops_user.pin
        assert serialized_user["is_staff"] == ops_user.is_staff
        assert serialized_user["is_superuser"] == ops_user.is_superuser
        assert serialized_user["is_active"]
