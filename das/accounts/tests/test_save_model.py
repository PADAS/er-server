from unittest.mock import MagicMock, patch

import pytest

from django.contrib.admin import site
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from accounts.admin import UserAdmin

User = get_user_model()


@pytest.fixture
def fake_request():
    return RequestFactory().post("/")


@pytest.fixture
def user_admin():
    return UserAdmin(User, site)


@pytest.fixture
def user_with_email(db):
    return User.objects.create_user(
        username="newuser",
        email="newuser@example.com",
        is_active=True,
    )


@pytest.fixture
def user_without_email(db):
    return User.objects.create_user(
        username="newuser",
        is_active=True,
    )


@pytest.fixture
def form():
    mock = MagicMock()
    mock.cleaned_data = {"password1": "", "linked_subject": None}
    return mock


@pytest.fixture
def mock_super_save_model():
    # Stubbed out to avoid pulling in the full Django admin save machinery.
    # These tests are establishing baseline coverage for UserAdmin.save_model
    # ahead of adding new IdP behavior — not attempting to integration-test
    # the parent class. Worth revisiting if save_model is ever refactored.
    with patch("django.contrib.auth.admin.UserAdmin.save_model"):
        yield


@pytest.fixture
def mock_send_reset_email(user_admin):
    # send_reset_email wraps Django's PasswordResetForm, which has its own
    # test surface. We mock it here because these tests care about *when*
    # a reset is triggered, not the mechanics of the reset email itself.
    # A future improvement could let this run for real with proper fixtures.
    with patch.object(user_admin, "send_reset_email") as mock:
        yield mock


@pytest.mark.django_db
class TestSaveModelNonIdp:

    class TestShouldResetPassword:

        class TestChangeIsTrue:

            @pytest.mark.parametrize(
                "password1,has_usable",
                [
                    ("", False),
                    ("", True),
                    ("pass", False),
                    ("pass", True),
                ],
            )
            def test_never_resets(
                self,
                user_admin,
                fake_request,
                user_with_email,
                form,
                mock_super_save_model,
                mock_send_reset_email,
                password1,
                has_usable,
            ):
                if has_usable:
                    user_with_email.set_password("existing-password")
                else:
                    user_with_email.set_unusable_password()
                form.cleaned_data["password1"] = password1

                original_password = user_with_email.password
                user_admin.save_model(fake_request, user_with_email, form, change=True)

                assert user_with_email.password == original_password
                mock_send_reset_email.assert_not_called()

        class TestChangeIsFalse:

            class TestNoPasswordSupplied:

                @pytest.mark.parametrize("has_usable", [False, True])
                def test_always_resets(
                    self,
                    user_admin,
                    fake_request,
                    user_with_email,
                    form,
                    mock_super_save_model,
                    mock_send_reset_email,
                    has_usable,
                ):
                    if has_usable:
                        user_with_email.set_password("existing-password")
                    else:
                        user_with_email.set_unusable_password()
                    original_password = user_with_email.password
                    user_admin.save_model(fake_request, user_with_email, form, change=False)

                    assert user_with_email.has_usable_password()
                    assert user_with_email.password != original_password
                    mock_send_reset_email.assert_called_once_with(fake_request, user_with_email)

            class TestPasswordSupplied:

                def test_resets_when_unusable_password(
                    self, user_admin, fake_request, user_with_email, form, mock_super_save_model, mock_send_reset_email
                ):
                    user_with_email.set_unusable_password()
                    original_password = user_with_email.password
                    form.cleaned_data["password1"] = "supplied-password"
                    user_admin.save_model(fake_request, user_with_email, form, change=False)

                    assert user_with_email.has_usable_password()
                    assert user_with_email.password != original_password
                    mock_send_reset_email.assert_called_once_with(fake_request, user_with_email)

                def test_does_not_reset_when_usable_password(
                    self, user_admin, fake_request, user_with_email, form, mock_super_save_model, mock_send_reset_email
                ):
                    user_with_email.set_password("existing-password")
                    original_password = user_with_email.password
                    form.cleaned_data["password1"] = "supplied-password"
                    user_admin.save_model(fake_request, user_with_email, form, change=False)

                    assert user_with_email.password == original_password
                    mock_send_reset_email.assert_not_called()

            def test_no_reset_when_no_email(
                self, user_admin, fake_request, user_without_email, form, mock_super_save_model, mock_send_reset_email
            ):
                user_without_email.set_unusable_password()
                user_admin.save_model(fake_request, user_without_email, form, change=False)

                # password was set, proving should_reset_password was True —
                # the only reason we didn't send is the missing email
                assert user_without_email.has_usable_password()
                mock_send_reset_email.assert_not_called()

    class TestLinkedSubject:

        def test_associates_subject_with_user(
            self, user_admin, fake_request, user_with_email, form, mock_super_save_model, mock_send_reset_email
        ):
            subject = MagicMock()
            subject.linked_user = None
            form.cleaned_data["linked_subject"] = subject

            user_admin.save_model(fake_request, user_with_email, form, change=False)

            assert subject.linked_user == user_with_email
            subject.save.assert_called_once()

        def test_already_linked_subject_is_not_resaved(
            self, user_admin, fake_request, user_with_email, form, mock_super_save_model, mock_send_reset_email
        ):
            subject = MagicMock()
            subject.linked_user = user_with_email
            form.cleaned_data["linked_subject"] = subject

            user_admin.save_model(fake_request, user_with_email, form, change=False)

            subject.save.assert_not_called()
