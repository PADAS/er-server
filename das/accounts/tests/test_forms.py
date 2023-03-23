import pytest

from accounts.forms import UserAdditionalForm


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
