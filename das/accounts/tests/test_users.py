import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant
from faker import Faker

from django.forms import ValidationError

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

    def test_form_validation_prevents_deactivating_user_with_alert_rules(self, das_tenant):
        """Test that form validation prevents deactivating user with alert rules"""
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

        # Form should not be valid due to alert rules validation
        assert not form.is_valid()
        assert "is_active" in form.errors
        assert "alert rule(s) configured" in form.errors["is_active"][0]
        assert "Test Alert Rule 1" in form.errors["is_active"][0]
        assert "Test Alert Rule 2" in form.errors["is_active"][0]

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

    def test_changelist_view_includes_alert_rules_data(self, das_tenant):
        """Test that changelist view includes alert rules data for JavaScript"""
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

        # Test the changelist view
        admin = UserAdmin(User, None)

        # Mock request object
        class MockRequest:
            pass

        request = MockRequest()

        # Call changelist_view
        response = admin.changelist_view(request)

        # Check that the response has the alert rules data
        assert hasattr(response, "context_data")
        assert "user_alert_rules" in response.context_data

        # Parse the JSON data
        user_alert_rules = json.loads(response.context_data["user_alert_rules"])

        # Check that user with rules has alert rules data
        assert str(user_with_rules.id) in user_alert_rules
        assert user_alert_rules[str(user_with_rules.id)]["count"] == 1
        assert user_alert_rules[str(user_with_rules.id)]["titles"] == ["Test Alert Rule"]

        # Check that user without rules has no alert rules data
        assert str(user_without_rules.id) not in user_alert_rules
