import pytest

from accounts.forms import CustomUserCreationForm, UserAdditionalForm
from accounts.models import User


@pytest.mark.django_db
class TestCustomUserCreationForm:
    @pytest.mark.parametrize("pin", ["1234", "0000", "0012"])
    def test_create_user_with_valid_pin(self, pin):
        form = CustomUserCreationForm(data={"username": "username", "pin": pin})

        form.is_valid()

        assert not form.errors

    def test_create_user_with_empty_pin(self):
        form = CustomUserCreationForm(data={"username": "username"})

        form.is_valid()

        assert not form.errors

    def test_create_user_with_string_pin(self):
        form = CustomUserCreationForm(data={"username": "username", "pin": "this"})

        form.is_valid()

        assert form.errors["pin"][0] == "The value should be four digits."

    def test_create_user_with_long_pin(self):
        form = CustomUserCreationForm(data={"username": "username", "pin": 123456})

        form.is_valid()

        assert form.errors["pin"][0] == "The size should be four digits."

    @pytest.mark.parametrize("pin", [12, 0])
    def test_create_user_with_short_pin(self, pin):
        form = CustomUserCreationForm(data={"username": "username", "pin": pin})

        form.is_valid()

        assert form.errors["pin"][0] == "The size should be four digits."

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_create_user_rejected_by_xss_protection(self, field_name):
        form = CustomUserCreationForm(data={"username": "username", field_name: "<script>alert('boo')</script>"})

        form.is_valid()

        assert (
            form.errors[field_name][0]
            == "The field contains invalid characters. Only alphanumeric characters and period are allowed."
        )

    @pytest.mark.parametrize("invalid_name", ["`", "-", "<", ">", ";", "$", "@", "(", ")"])
    def test_special_characters_are_not_allowed_on_first_name_field(self, invalid_name):
        form = CustomUserCreationForm(data={"username": "username", "first_name": invalid_name})

        form.is_valid()

        assert (
            form.errors["first_name"][0]
            == "The field contains invalid characters. Only alphanumeric characters and period are allowed."
        )

    def test_create_user_with_duplicate_pin(self):
        user = User.objects.first()
        user.pin = "1234"
        user.save()
        form = CustomUserCreationForm(data={"username": "username", "pin": "1234"})

        form.is_valid()

        assert form.errors["pin"][0] == "User PINs must be unique, please select another PIN value."


@pytest.mark.django_db
class TestUserAdditionalForm:
    @pytest.mark.parametrize("pin", ["1234", "0000", "0012"])
    def test_create_user_with_valid_pin(self, pin):
        form = UserAdditionalForm(data={"username": "username", "pin": pin})

        form.is_valid()

        assert not form.errors

    def test_create_user_with_empty_pin(self):
        form = UserAdditionalForm(data={"username": "username"})

        form.is_valid()

        assert not form.errors

    def test_create_user_with_string_pin(self):
        form = UserAdditionalForm(data={"username": "username", "pin": "this"})

        form.is_valid()

        assert form.errors["pin"][0] == "The value should be four digits."

    def test_create_user_with_long_pin(self):
        form = UserAdditionalForm(data={"username": "username", "pin": 123456})

        form.is_valid()

        assert form.errors["pin"][0] == "The size should be four digits."

    @pytest.mark.parametrize("pin", [12, 0])
    def test_create_user_with_short_pin(self, pin):
        form = UserAdditionalForm(data={"username": "username", "pin": pin})

        form.is_valid()

        assert form.errors["pin"][0] == "The size should be four digits."

    @pytest.mark.parametrize("field_name", ["first_name", "last_name"])
    def test_create_user_rejected_by_xss_protection(self, field_name):
        form = UserAdditionalForm(data={"username": "username", field_name: "<script>alert('boo')</script>"})

        form.is_valid()

        assert (
            form.errors[field_name][0]
            == "The field contains invalid characters. Only alphanumeric characters and period are allowed."
        )

    @pytest.mark.parametrize("invalid_name", ["`", "-", "<", ">", ";", "$", "@", "(", ")"])
    def test_special_characters_are_not_allowed_on_first_name_field(self, invalid_name):
        form = UserAdditionalForm(data={"username": "username", "first_name": invalid_name})

        form.is_valid()

        assert (
            form.errors["first_name"][0]
            == "The field contains invalid characters. Only alphanumeric characters and period are allowed."
        )

    def test_create_user_with_duplicate_pin(self):
        user = User.objects.first()
        user.pin = "1234"
        user.save()
        form = UserAdditionalForm(data={"username": "username", "pin": "1234"})

        form.is_valid()

        assert form.errors["pin"][0] == "User PINs must be unique, please select another PIN value."

    def test_edit_existing_user_with_pin_set(self):
        user = User.objects.first()
        user.username = "cosme"
        user.first_name = "Homero"
        user.last_name = "Simpson"
        user.pin = "1234"
        user.save()

        form = UserAdditionalForm(
            data={"username": "cosme", "first_name": "Cosme", "last_name": "Fulanito", "pin": "1234"}
        )
        form.is_valid()

        assert "pin" not in form.errors
