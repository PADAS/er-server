from unittest.mock import MagicMock, patch

import pytest

from django.contrib.admin import site
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import RequestFactory
from django.urls import reverse

from accounts.account_linker import ACCOUNT_LINKER_LANDING_URL_NAME
from accounts.admin import UserAdmin

User = get_user_model()


@pytest.fixture
def fake_request():
    request = RequestFactory().post("/")
    request.build_absolute_uri = lambda path: f"https://testsite.pamdas.org{path}"
    return request


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
    with patch.object(user_admin, "_send_reset_email") as mock:
        yield mock


@pytest.mark.django_db
class TestSaveModelNonIdp:

    @pytest.fixture(autouse=True)
    def _run_on_commit_callbacks(self):
        """Execute on_commit callbacks immediately. These tests run inside a
        rolled-back transaction (default django_db), so on_commit callbacks
        would otherwise never fire."""
        with patch("accounts.admin.transaction.on_commit", side_effect=lambda func: func()):
            yield

    @pytest.fixture(autouse=True)
    def non_idp_tenant_settings(self):
        mock = MagicMock()
        mock.feature_flags.require_idp = False
        with patch("accounts.admin.get_tenant_settings", return_value=mock):
            yield mock

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


@pytest.mark.django_db
class TestSaveModelWithIdp:

    @pytest.fixture(autouse=True)
    def _run_on_commit_callbacks(self):
        with patch("accounts.admin.transaction.on_commit", side_effect=lambda func: func()):
            yield

    @pytest.fixture
    def magic_link_token(self):
        return "test-token"

    @pytest.fixture(autouse=True)
    def fake_account_linker(self, magic_link_token):
        with patch("accounts.admin.create_magic_link_token", return_value=magic_link_token):
            yield

    @pytest.fixture(autouse=True)
    def mock_current_tenant(self):
        with patch("accounts.admin.get_current_tenant") as mock:
            mock.return_value.domain = "testsite.pamdas.org"
            yield mock

    @pytest.fixture(autouse=True)
    def _default_from_email(self, settings):
        settings.DEFAULT_FROM_EMAIL = "noreply@example.com"

    @pytest.fixture(autouse=True)
    def idp_tenant_settings(self):
        mock = MagicMock()
        mock.feature_flags.require_idp = True
        with patch("accounts.admin.get_tenant_settings", return_value=mock):
            yield mock

    @pytest.fixture
    def sent_invitation_email(
        self,
        user_admin,
        fake_request,
        user_with_email,
        form,
        mock_super_save_model,
        mailoutbox,
    ):
        user_admin.save_model(fake_request, user_with_email, form, change=False)
        assert len(mailoutbox) == 1, f"Expected 1 email, got {len(mailoutbox)}"
        return mailoutbox[0]

    def test_sent_to_user_email_address(self, sent_invitation_email, user_with_email):
        assert sent_invitation_email.to == [user_with_email.email]

    def test_sent_from_default_from_email(self, sent_invitation_email):
        assert sent_invitation_email.from_email == "noreply@example.com"

    def test_subject(self, sent_invitation_email):
        assert sent_invitation_email.subject == "Your invitation to testsite.pamdas.org"

    def test_body_contains_invitation_url_on_its_own_line(self, sent_invitation_email, magic_link_token):
        expected_url = f"https://testsite.pamdas.org{reverse(ACCOUNT_LINKER_LANDING_URL_NAME)}?token={magic_link_token}"
        assert expected_url in sent_invitation_email.body.splitlines()

    def test_new_user_has_unusable_password(
        self, user_admin, fake_request, user_with_email, form, mock_super_save_model
    ):
        # Simulate the admin having entered a password in the creation form.
        # On an IdP tenant, save_model should override this to unusable so the
        # user can only authenticate via ER IdP.
        user_with_email.set_password("admin-entered-password")

        user_admin.save_model(fake_request, user_with_email, form, change=False)

        assert not user_with_email.has_usable_password()

    class TestShouldNotSendIdpEmail:

        def test_no_email_when_change_is_true(
            self,
            user_admin,
            fake_request,
            user_with_email,
            form,
            mock_super_save_model,
            mailoutbox,
        ):
            user_admin.save_model(fake_request, user_with_email, form, change=True)

            assert len(mailoutbox) == 0

        def test_no_email_when_user_has_no_email(
            self,
            user_admin,
            fake_request,
            user_without_email,
            form,
            mock_super_save_model,
            mailoutbox,
        ):
            user_admin.save_model(fake_request, user_without_email, form, change=False)

            assert len(mailoutbox) == 0


@pytest.mark.django_db(transaction=True)
class TestEmailDeferredToCommit:
    """Django admin's changeform_view wraps save_model in transaction.atomic().
    If that transaction rolls back (e.g. a signal handler raises), any email
    sent inline would already be delivered for a user that no longer exists.
    These tests simulate this by wrapping save_model in an atomic block that
    is rolled back, then asserting no email escaped the transaction boundary."""

    class Rollback(Exception):
        pass

    @pytest.fixture
    def user_with_email(self):
        # A mock user avoids hitting the DB (and the das_tenant FK) so that
        # transactional test isolation doesn't conflict with multi-tenant state.
        user = MagicMock()
        user.email = "newuser@example.com"
        user.has_usable_password.return_value = False
        return user

    @pytest.fixture(autouse=True)
    def _mock_super_save_model(self):
        with patch("django.contrib.auth.admin.UserAdmin.save_model"):
            yield

    def test_reset_email_not_sent_on_rollback(
        self, user_admin, fake_request, user_with_email, form, mock_send_reset_email
    ):
        mock = MagicMock()
        mock.feature_flags.require_idp = False
        with patch("accounts.admin.get_tenant_settings", return_value=mock):
            with pytest.raises(self.Rollback):
                with transaction.atomic():
                    user_admin.save_model(fake_request, user_with_email, form, change=False)
                    raise self.Rollback()

        mock_send_reset_email.assert_not_called()

    def test_invitation_email_not_sent_on_rollback(
        self, user_admin, fake_request, user_with_email, form, settings, mailoutbox
    ):
        settings.DEFAULT_FROM_EMAIL = "noreply@example.com"

        mock_ts = MagicMock()
        mock_ts.feature_flags.require_idp = True
        with patch("accounts.admin.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.admin.create_magic_link_token", return_value="test-token"):
                with patch("accounts.admin.get_current_tenant") as mock_tenant:
                    mock_tenant.return_value.domain = "testsite.pamdas.org"

                    with pytest.raises(self.Rollback):
                        with transaction.atomic():
                            user_admin.save_model(fake_request, user_with_email, form, change=False)
                            raise self.Rollback()

        assert len(mailoutbox) == 0
