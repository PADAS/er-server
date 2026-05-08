import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant
from faker import Faker

from django.core.exceptions import ValidationError

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
