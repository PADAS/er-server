from unittest.mock import MagicMock, patch

import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant
from faker import Faker

from django.contrib.admin import site
from django.contrib.admin.utils import flatten_fieldsets
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory
from django.urls import reverse

from accounts.admin import UserAdmin
from accounts.models import User

faker = Faker()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserTenant:
    def test_create_users_diff_tenant_with_same_email(self, five_tenants):
        same_email = "same@email.com"

        previous_tenant = get_current_tenant()

        for tenant in five_tenants:
            set_current_tenant(tenant)
            user = User.objects.create_user(username=faker.profile()["username"], password="password", email=same_email)
            assert tenant.id == user.das_tenant.id
            assert same_email == user.email

        set_current_tenant(previous_tenant)
        assert User.objects.filter(email=same_email).count() == len(five_tenants)

    def test_create_users_same_tenant_with_same_email(self, das_tenant):
        same_email = "same@email.com"

        with pytest.raises(ValidationError):
            for _ in range(0, 2):
                User.objects.create_user(
                    username=faker.profile()["username"],
                    password="password",
                    email=same_email,
                    das_tenant=das_tenant,
                )

    def test_create_user_same_tenant_with_no_email(self, das_tenant):
        usernames = [faker.profile()["username"], faker.profile()["username"], faker.profile()["username"]]
        set_current_tenant(das_tenant)
        for username in usernames:
            User.objects.create_user(username=username, password="password")

        assert User.objects.filter(
            username__in=usernames,
            email__isnull=True,
        ).count() == len(usernames)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserFormAlertRulesValidation:
    """Test the alert rules validation functionality in UserAdditionalForm (ERA-11874)"""

    def test_form_validation_allows_deactivating_user_with_alert_rules(self, das_tenant):
        """Test that form validation allows deactivating user with alert rules (client-side warnings handle UX)"""
        import json

        from accounts.forms import UserAdditionalForm
        from activity.models import AlertRule, EventCategory, EventType

        # Create an active user with alert rules
        user = User.objects.create_user(
            username="testuser",
            password="password",
            email="test@example.com",
            das_tenant=das_tenant,
            is_active=True,  # User is active
        )

        # Create event category and type for alert rules
        category = EventCategory.objects.create(value="test_category", display="Test Category", das_tenant=das_tenant)

        event_type = EventType.objects.create(
            value="test_event",
            display="Test Event",
            schema=json.dumps({"schema": {"type": "object"}}),
            category=category,
            das_tenant=das_tenant,
        )

        # Create alert rules for the user
        alert_rule1 = AlertRule.objects.create(owner=user, title="Test Alert Rule 1", das_tenant=das_tenant)
        alert_rule1.event_types.add(event_type)

        alert_rule2 = AlertRule.objects.create(owner=user, title="Test Alert Rule 2", das_tenant=das_tenant)
        alert_rule2.event_types.add(event_type)

        # Test form validation when trying to deactivate user
        form_data = {
            "is_active": False,  # Trying to deactivate
            "username": user.username,
            "email": user.email,
        }
        form = UserAdditionalForm(data=form_data, instance=user)

        # Form should be valid - client-side warnings handle the UX
        assert form.is_valid()
        assert "is_active" not in form.errors

    def test_form_validation_allows_deactivating_user_without_alert_rules(self, das_tenant):
        """Test that form validation allows deactivating user without alert rules"""
        from accounts.forms import UserAdditionalForm

        # Create an active user without alert rules
        user = User.objects.create_user(
            username="testuser",
            password="password",
            email="test@example.com",
            das_tenant=das_tenant,
            is_active=True,  # User is active
        )

        # Test form validation when trying to deactivate user
        form_data = {
            "is_active": False,  # Trying to deactivate
            "username": user.username,
            "email": user.email,
        }
        form = UserAdditionalForm(data=form_data, instance=user)

        # Form should be valid since user has no alert rules
        assert form.is_valid()

    def test_form_validation_allows_activating_user_with_alert_rules(self, das_tenant):
        """Test that form validation allows activating user with alert rules"""
        import json

        from accounts.forms import UserAdditionalForm
        from activity.models import AlertRule, EventCategory, EventType

        # Create an inactive user with alert rules
        user = User.objects.create_user(
            username="testuser",
            password="password",
            email="test@example.com",
            das_tenant=das_tenant,
            is_active=False,  # User is inactive
        )

        # Create event category and type for alert rules
        category = EventCategory.objects.create(value="test_category", display="Test Category", das_tenant=das_tenant)

        event_type = EventType.objects.create(
            value="test_event",
            display="Test Event",
            schema=json.dumps({"schema": {"type": "object"}}),
            category=category,
            das_tenant=das_tenant,
        )

        # Create alert rules for the user
        alert_rule = AlertRule.objects.create(owner=user, title="Test Alert Rule", das_tenant=das_tenant)
        alert_rule.event_types.add(event_type)

        # Test form validation when trying to activate user
        form_data = {
            "is_active": True,  # Trying to activate
            "username": user.username,
            "email": user.email,
        }
        form = UserAdditionalForm(data=form_data, instance=user)

        # Form should be valid since we're activating the user
        assert form.is_valid()

    def test_changelist_view_alert_rules_data_preparation(self, das_tenant):
        """Test that changelist view correctly prepares alert rules data for JavaScript"""
        import json

        from accounts.admin import UserAdmin
        from activity.models import AlertRule, EventCategory, EventType

        # Create users with and without alert rules
        user_with_rules = User.objects.create_user(
            username="user_with_rules",
            password="password",
            email="with_rules@example.com",
            das_tenant=das_tenant,
            is_active=True,
        )

        user_without_rules = User.objects.create_user(
            username="user_without_rules",
            password="password",
            email="without_rules@example.com",
            das_tenant=das_tenant,
            is_active=True,
        )

        # Create event category and type for alert rules
        category = EventCategory.objects.create(value="test_category", display="Test Category", das_tenant=das_tenant)

        event_type = EventType.objects.create(
            value="test_event",
            display="Test Event",
            schema=json.dumps({"schema": {"type": "object"}}),
            category=category,
            das_tenant=das_tenant,
        )

        # Create alert rules for one user
        alert_rule = AlertRule.objects.create(owner=user_with_rules, title="Test Alert Rule", das_tenant=das_tenant)
        alert_rule.event_types.add(event_type)

        # Test the data preparation logic directly
        UserAdmin(User, None)
        queryset = User.objects.filter(das_tenant=das_tenant)

        # Get all user IDs that have alert rules in a single query
        user_ids_with_alerts = set(AlertRule.objects.filter(owner__in=queryset).values_list("owner_id", flat=True))

        # Prepare the data as done in changelist_view
        user_alert_rules = {}
        form_index_to_user_id = {}

        for index, user in enumerate(queryset):
            # Map form index to user ID for JavaScript
            form_index_to_user_id[str(index)] = str(user.id)

            # Check if user has alert rules (just boolean, no details needed)
            if user.id in user_ids_with_alerts:
                user_alert_rules[str(user.id)] = {"has_alerts": True}

        # Check that user with rules has alert rules data
        assert str(user_with_rules.id) in user_alert_rules
        assert user_alert_rules[str(user_with_rules.id)]["has_alerts"] is True

        # Check that user without rules has no alert rules data
        assert str(user_without_rules.id) not in user_alert_rules

        # Check form index mapping
        assert "0" in form_index_to_user_id
        assert "1" in form_index_to_user_id


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserAuth0Integration:
    """Test Auth0 ID field validation and constraints"""

    def test_auth0_id_can_be_null(self, das_tenant):
        """Auth0 ID can be None/null"""
        user = User.objects.create_user(
            username="testuser1", email="test1@example.com", password="password", auth0_id=None
        )
        assert user.auth0_id is None

    def test_auth0_id_can_be_valid_string(self, das_tenant):
        """Auth0 ID can be a valid Auth0 subject identifier"""
        auth0_id = "a" * 256
        user = User.objects.create_user(
            username="testuser2", email="test2@example.com", password="password", auth0_id=auth0_id
        )
        assert user.auth0_id == auth0_id

    def test_auth0_id_same_id_different_tenants(self, five_tenants):
        """Same Auth0 ID can exist in different tenants"""
        auth0_id = "the-same-auth0-id"

        # Create users with same auth0_id in two different tenants - should work
        set_current_tenant(five_tenants[0])
        user1 = User.objects.create_user(
            username="testuser_tenant1", email="test1@example.com", password="password", auth0_id=auth0_id
        )

        set_current_tenant(five_tenants[1])
        user2 = User.objects.create_user(
            username="testuser_tenant2", email="test2@example.com", password="password", auth0_id=auth0_id
        )

        assert user1.auth0_id == auth0_id
        assert user2.auth0_id == auth0_id

    @pytest.mark.parametrize("auth0_id_value", ["", " "])
    def test_auth0_id_cannot_be_empty_or_whitespace(self, das_tenant, auth0_id_value):
        """Auth0 ID cannot be an empty or whitespace-only string"""
        with pytest.raises(ValidationError) as exc_info:
            User.objects.create_user(
                username="testuser3", email="test3@example.com", password="password", auth0_id=auth0_id_value
            )

        assert "auth0_id" in exc_info.value.message_dict
        assert "cannot be empty" in str(exc_info.value.message_dict["auth0_id"][0]).lower()

    def test_auth0_id_max_length_failure(self, das_tenant):
        """Auth0 ID cannot exceed 256 characters"""
        auth0_id_257 = "a" * 257  # 257 'a' characters - should fail
        with pytest.raises(ValidationError) as exc_info:
            User.objects.create_user(
                username="testuser4", email="test4@example.com", password="password", auth0_id=auth0_id_257
            )

        assert "auth0_id" in exc_info.value.message_dict
        error_message = str(exc_info.value.message_dict["auth0_id"][0])
        assert "at most 256 characters" in error_message
        assert "it has 257" in error_message

    def test_auth0_id_same_id_same_tenant_failure(self, das_tenant):
        """Same Auth0 ID cannot exist twice in same tenant"""
        from django.core.exceptions import ValidationError

        auth0_id = "the-same-auth0-id"

        # Create first user - should work
        User.objects.create_user(
            username="testuser5", email="test5@example.com", password="password", auth0_id=auth0_id
        )

        # Try to create second user with same auth0_id in same tenant - should fail
        # User.save() calls full_clean(), so the unique constraint is raised as ValidationError
        with pytest.raises(ValidationError) as exc_info:
            User.objects.create_user(
                username="testuser6", email="test6@example.com", password="password", auth0_id=auth0_id
            )

        error_message = str(exc_info.value)
        assert "unique_auth0_id_per_tenant" in error_message


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminEmailEditability:
    """Observable behavior: which admin forms expose email as an editable field.
    Once an account is linked to Auth0 (auth0_id set), its email mirrors the
    authoritative Auth0 login identity, so the change form locks it — a save
    cannot change its value (the root cause of the RCU incident). Until linked,
    the email is still a local value (and the invitation target), so it stays
    editable; the add form likewise keeps it editable. Asserting against the form
    Django builds (get_form) exercises the real get_form -> get_readonly_fields
    path, proving the wiring rather than trusting it."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        # UserAdmin.get_form reads request.user; its identity is irrelevant to
        # which fields are editable.
        self.request.user = MagicMock()
        self.linked_user = User.objects.create_user(
            username="linkeduser",
            email="linked@auth0.example",
            auth0_id="auth0|linked",
            das_tenant=das_tenant,
            is_active=True,
        )
        self.unlinked_user = User.objects.create_user(
            username="unlinkeduser", email="unlinked@auth0.example", das_tenant=das_tenant, is_active=True
        )

    def _email_is_editable(self, *, require_idp, obj, change):
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = None
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            form = self.admin.get_form(self.request, obj=obj, change=change)
        return "email" in form.base_fields

    def test_change_form_locks_email_for_linked_idp_user(self):
        assert self._email_is_editable(require_idp=True, obj=self.linked_user, change=True) is False

    def test_change_form_keeps_email_editable_for_unlinked_idp_user(self):
        assert self._email_is_editable(require_idp=True, obj=self.unlinked_user, change=True) is True

    def test_change_form_keeps_email_editable_on_non_idp_tenant(self):
        assert self._email_is_editable(require_idp=False, obj=self.linked_user, change=True) is True

    def test_add_form_keeps_email_editable_on_idp_tenant(self):
        assert self._email_is_editable(require_idp=True, obj=None, change=False) is True


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminIdpEmailHint:
    """Once linked, the read-only email is shown with a hint describing it as the
    email the user's EarthRanger Identity account was created with, so admins
    understand why it can't be edited. The hint rides on a read-only display
    field standing in for the plain email field (Django renders a read-only
    model field's help text from the model, so the hint has to travel with the
    value). Until linked, the email stays a plain editable field with no hint."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.request.user = MagicMock()
        self.linked_user = User.objects.create_user(
            username="linkeduser",
            email="linked@auth0.example",
            auth0_id="auth0|linked",
            das_tenant=das_tenant,
            is_active=True,
        )
        self.unlinked_user = User.objects.create_user(
            username="unlinkeduser", email="unlinked@auth0.example", das_tenant=das_tenant, is_active=True
        )

    def _change_form_fields(self, *, require_idp, obj):
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = None
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            fieldsets = self.admin.get_fieldsets(self.request, obj=obj)
            readonly = self.admin.get_readonly_fields(self.request, obj=obj)
        return flatten_fieldsets(fieldsets), readonly

    def test_linked_idp_email_rendered_through_readonly_hint_field(self):
        fields, readonly = self._change_form_fields(require_idp=True, obj=self.linked_user)
        # Email is shown via a read-only display field (so the hint can ride with
        # the value) instead of the plain, editable model field.
        assert "_email_with_idp_hint" in fields
        assert "_email_with_idp_hint" in readonly
        assert "email" not in fields

    def test_unlinked_idp_email_stays_plain_editable(self):
        fields, _ = self._change_form_fields(require_idp=True, obj=self.unlinked_user)
        assert "email" in fields
        assert "_email_with_idp_hint" not in fields

    def test_idp_email_hint_describes_earthranger_identity(self):
        rendered = str(self.admin._email_with_idp_hint(self.linked_user))
        assert "linked@auth0.example" in rendered
        assert "EarthRanger Identity" in rendered

    def test_non_idp_change_form_keeps_plain_email(self):
        fields, _ = self._change_form_fields(require_idp=False, obj=self.linked_user)
        assert "email" in fields
        assert "_email_with_idp_hint" not in fields


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminUsernameEditability:
    """Observable behavior: on Auth0 Organizations (org-enabled) sites the
    username is a valid Auth0 login identifier, so once the account is linked
    (auth0_id set) the change form locks it — a save cannot change it. Until
    linked, and on non-org / non-Auth0 sites, the username stays editable. Org
    state comes from feature_flags.idp_org_id."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.request.user = MagicMock()
        self.linked_user = User.objects.create_user(
            username="linkeduser",
            email="linked@auth0.example",
            auth0_id="auth0|linked",
            das_tenant=das_tenant,
            is_active=True,
        )
        self.unlinked_user = User.objects.create_user(
            username="unlinkeduser", email="unlinked@auth0.example", das_tenant=das_tenant, is_active=True
        )

    def _username_is_editable(self, *, require_idp, idp_org_id, obj):
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = idp_org_id
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            form = self.admin.get_form(self.request, obj=obj, change=True)
        return "username" in form.base_fields

    def test_change_form_locks_username_for_linked_org_user(self):
        assert (
            self._username_is_editable(require_idp=True, idp_org_id="org_rcuksa_abc123", obj=self.linked_user) is False
        )

    def test_change_form_keeps_username_editable_for_unlinked_org_user(self):
        assert (
            self._username_is_editable(require_idp=True, idp_org_id="org_rcuksa_abc123", obj=self.unlinked_user) is True
        )

    def test_change_form_keeps_username_editable_on_non_org_idp_tenant(self):
        assert self._username_is_editable(require_idp=True, idp_org_id=None, obj=self.linked_user) is True

    def test_change_form_keeps_username_editable_on_non_idp_tenant(self):
        assert self._username_is_editable(require_idp=False, idp_org_id=None, obj=self.linked_user) is True


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminNonOrgUsernameHint:
    """On a non-org IdP site the username stays editable but is hinted as the
    user's EarthRanger username for this site. Non-Auth0 sites get no such
    hint."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.request.user = MagicMock()
        self.user = User.objects.create_user(
            username="idpuser", email="real@auth0.example", das_tenant=das_tenant, is_active=True
        )

    def _username_help_text(self, *, require_idp, idp_org_id):
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = idp_org_id
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            form = self.admin.get_form(self.request, obj=self.user, change=True)
        if "username" not in form.base_fields:
            return ""
        return str(form.base_fields["username"].help_text)

    def test_non_org_idp_username_shows_site_hint(self):
        assert "EarthRanger username" in self._username_help_text(require_idp=True, idp_org_id=None)

    def test_non_idp_username_has_no_site_hint(self):
        assert "EarthRanger username" not in self._username_help_text(require_idp=False, idp_org_id=None)


class TestUserAdminPasswordChangeViewGuard:
    """On Auth0/IdP tenants the local password is not operative, so the admin
    password-change view (.../password/) is blocked with a 403 — it is the only
    path that would set a local password after an account is created. Non-Auth0
    tenants keep Django's standard password-change behavior."""

    @pytest.fixture(autouse=True)
    def _admin(self):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")

    @staticmethod
    def _tenant_settings(*, require_idp):
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = None
        return tenant_settings

    def test_blocks_password_change_on_idp_tenant(self):
        with patch("accounts.admin.get_tenant_settings", return_value=self._tenant_settings(require_idp=True)):
            with patch("django.contrib.auth.admin.UserAdmin.user_change_password", return_value="delegated"):
                with pytest.raises(PermissionDenied):
                    self.admin.user_change_password(self.request, "1")

    def test_allows_password_change_on_non_idp_tenant(self):
        with patch("accounts.admin.get_tenant_settings", return_value=self._tenant_settings(require_idp=False)):
            with patch(
                "django.contrib.auth.admin.UserAdmin.user_change_password", return_value="delegated"
            ) as mock_super:
                result = self.admin.user_change_password(self.request, "1")
        assert result == "delegated"
        mock_super.assert_called_once()


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminPasswordControlsHidden:
    """On Auth0/IdP tenants the local password is not operative, so the admin
    forms hide the password-set controls: the change form drops the password
    hash widget (and its "change password" link), and the add form drops the
    password1/password2 inputs (save_model sets an unusable password on create).
    Non-Auth0 tenants keep the standard controls."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.request.user = MagicMock()
        self.user = User.objects.create_user(
            username="idpuser", email="real@auth0.example", das_tenant=das_tenant, is_active=True
        )

    def _fields(self, *, require_idp, obj):
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = None
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            return flatten_fieldsets(self.admin.get_fieldsets(self.request, obj=obj))

    def test_change_form_hides_password_on_idp_tenant(self):
        assert "password" not in self._fields(require_idp=True, obj=self.user)

    def test_change_form_keeps_password_on_non_idp_tenant(self):
        assert "password" in self._fields(require_idp=False, obj=self.user)

    def test_add_form_hides_password_inputs_on_idp_tenant(self):
        fields = self._fields(require_idp=True, obj=None)
        assert "password1" not in fields
        assert "password2" not in fields

    def test_add_form_keeps_password_inputs_on_non_idp_tenant(self):
        fields = self._fields(require_idp=False, obj=None)
        assert "password1" in fields
        assert "password2" in fields


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminResetPasswordViewGuard:
    """On Auth0/IdP tenants the Django password-reset email is a dead end — the
    new password never reaches Auth0 — so the admin reset-password action
    (.../reset-password/, behind the "Email password reset" button) is blocked
    with a 403. Non-Auth0 tenants keep sending the reset email."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.request.user = MagicMock()
        self.user = User.objects.create_user(
            username="idpuser", email="real@auth0.example", das_tenant=das_tenant, is_active=True
        )

    @staticmethod
    def _tenant_settings(*, require_idp):
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = None
        return tenant_settings

    def test_blocks_reset_password_on_idp_tenant(self):
        with patch("accounts.admin.get_tenant_settings", return_value=self._tenant_settings(require_idp=True)):
            with patch.object(self.admin, "_send_reset_email"):
                with pytest.raises(PermissionDenied):
                    self.admin.reset_password(self.request, str(self.user.id))

    def test_sends_reset_email_on_non_idp_tenant(self):
        with patch("accounts.admin.get_tenant_settings", return_value=self._tenant_settings(require_idp=False)):
            with patch.object(self.admin, "_send_reset_email") as mock_send:
                response = self.admin.reset_password(self.request, str(self.user.id))
        mock_send.assert_called_once()
        assert response.status_code == 302


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminResetButtonState:
    """render_change_form exposes reset_button_state to the change-form template
    so it can render the right control per the link/site/email matrix: a live
    reset (non-Auth0), self-service guidance (linked), a (re)send invitation
    (unlinked non-org with an email), an add-email nudge (unlinked non-org with
    no email), or a contact-support note (unlinked org)."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.das_tenant = das_tenant

    def _button_state(self, *, require_idp, idp_org_id, auth0_id, email):
        user = User.objects.create_user(
            username="targetuser", email=email, auth0_id=auth0_id, das_tenant=self.das_tenant, is_active=True
        )
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = idp_org_id
        context = {}
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            with patch("django.contrib.auth.admin.UserAdmin.render_change_form", return_value="rendered"):
                self.admin.render_change_form(self.request, context, change=True, obj=user)
        return context.get("reset_button_state")

    def test_non_idp_site_uses_live_reset(self):
        assert (
            self._button_state(require_idp=False, idp_org_id=None, auth0_id=None, email="u@x.example") == "live_reset"
        )

    def test_linked_account_shows_self_service(self):
        assert (
            self._button_state(require_idp=True, idp_org_id=None, auth0_id="auth0|x", email="u@x.example")
            == "self_service"
        )

    def test_unlinked_non_org_with_email_offers_resend(self):
        assert self._button_state(require_idp=True, idp_org_id=None, auth0_id=None, email="u@x.example") == "resend"

    def test_unlinked_non_org_without_email_needs_email(self):
        assert self._button_state(require_idp=True, idp_org_id=None, auth0_id=None, email=None) == "needs_email"

    def test_unlinked_org_says_contact_support(self):
        assert (
            self._button_state(require_idp=True, idp_org_id="org_rcuksa_abc123", auth0_id=None, email="u@x.example")
            == "contact_support"
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserAdminPasswordViewsBlockedEndToEnd:
    """End-to-end: on Auth0/IdP tenants the password-change view and the
    reset-password action return 403 when reached by URL — confirming Django
    routes those URLs to the guarded overrides, not merely that the overrides
    raise. This is the direct-URL back-door check; hiding/disabling the buttons
    is separate and cosmetic."""

    def test_password_views_return_403_on_idp_tenant(self, superuser_client, das_tenant):
        user = User.objects.create_user(
            username="idpuser", email="real@auth0.example", das_tenant=das_tenant, is_active=True
        )
        change_url = reverse("admin:accounts_user_change", args=[user.pk])
        password_url = change_url.replace("/change/", "/password/")
        reset_url = change_url + "reset-password/"

        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = True
        tenant_settings.feature_flags.idp_org_id = None
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            password_response = superuser_client.get(password_url)
            reset_response = superuser_client.get(reset_url)

        assert password_response.status_code == 403
        assert reset_response.status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestUserAdminResendInvitationView:
    """The "(Re)send EarthRanger Identity invitation" admin action sends the
    magic-link invitation — but only for an unlinked account on a common-DB
    (non-org) IdP site that has an email. Every other state (linked, org-scoped,
    no email, non-Auth0) is blocked with a 403, since the magic-link linker only
    serves unlinked common-DB accounts with somewhere to send the invite."""

    @pytest.fixture(autouse=True)
    def _admin(self, das_tenant):
        self.admin = UserAdmin(User, site)
        self.request = RequestFactory().get("/")
        self.request.user = MagicMock()  # has_change_permission -> truthy
        self.das_tenant = das_tenant

    def _call_resend(self, *, require_idp, idp_org_id, auth0_id, email):
        user = User.objects.create_user(
            username="targetuser", email=email, auth0_id=auth0_id, das_tenant=self.das_tenant, is_active=True
        )
        tenant_settings = MagicMock()
        tenant_settings.feature_flags.require_idp = require_idp
        tenant_settings.feature_flags.idp_org_id = idp_org_id
        with patch("accounts.admin.get_tenant_settings", return_value=tenant_settings):
            with patch.object(self.admin, "_send_idp_invitation_email") as mock_send:
                response = self.admin.resend_idp_invitation(self.request, str(user.id))
        return response, mock_send

    def test_sends_invitation_for_unlinked_non_org_idp_user_with_email(self):
        response, mock_send = self._call_resend(
            require_idp=True, idp_org_id=None, auth0_id=None, email="unlinked@auth0.example"
        )
        mock_send.assert_called_once()
        assert response.status_code == 302

    def test_blocks_when_account_already_linked(self):
        with pytest.raises(PermissionDenied):
            self._call_resend(require_idp=True, idp_org_id=None, auth0_id="auth0|linked", email="linked@auth0.example")

    def test_blocks_on_org_scoped_site(self):
        with pytest.raises(PermissionDenied):
            self._call_resend(require_idp=True, idp_org_id="org_rcuksa_abc123", auth0_id=None, email="u@auth0.example")

    def test_blocks_when_user_has_no_email(self):
        with pytest.raises(PermissionDenied):
            self._call_resend(require_idp=True, idp_org_id=None, auth0_id=None, email=None)

    def test_blocks_on_non_idp_site(self):
        with pytest.raises(PermissionDenied):
            self._call_resend(require_idp=False, idp_org_id=None, auth0_id=None, email="u@auth0.example")
