import pytest

from django.urls import reverse

from accounts.models.permissionset import PermissionSet
from activity.models import EventCategory
from revision.middleware import request_context


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEventCategorySignals:
    @pytest.mark.parametrize("value", ["test_1"])
    def test_create_dynamic_permissions_for_new_category(self, value):
        data = {"value": value, "display": value, "flag": "user"}
        event = EventCategory.objects.create(**data)

        permission_set = PermissionSet.objects.get(name=event.auto_permissionset_name)
        geo_permission_set = PermissionSet.objects.get(name=event.auto_geographic_permission_set_name)

        assert permission_set.permissions.count() == 4
        assert geo_permission_set.permissions.count() == 4

    @pytest.mark.parametrize(
        "data",
        [
            {
                "value": "das 8242",
                "display": "",
                "flag": "user",
                "expected": "das-8242",
            },
            {
                "value": "DAS 8242",
                "display": "",
                "flag": "user",
                "expected": "das-8242",
            },
            {
                "value": "new category",
                "display": "",
                "flag": "user",
                "expected": "new-category",
            },
            {
                "value": "New category",
                "display": "",
                "flag": "user",
                "expected": "new-category",
            },
            {
                "value": "my C@tegory",
                "display": "",
                "flag": "user",
                "expected": "my-ctegory",
            },
        ],
    )
    def test_slugify_event_category_value_field_for_new_categories(self, data):
        expected = data.pop("expected")
        print(f"\nExpected: {expected}")
        event = EventCategory.objects.create(**data)
        print(f"Event.value: {event.value}\n")
        assert event.value == expected

    def test_not_slugify_event_category_value_field_for_existing_categories(self, basic_event_categories):
        for category in EventCategory.objects.all():
            pre_value = category.value
            new_display_value = f"{pre_value}_new"
            category.display = new_display_value
            category.save()

            assert pre_value == category.value
            assert new_display_value == category.display

    def test_new_category_adds_request_user_to_permissionsets(self, superuser_client):
        """Test that when a new EventCategory is created via API with a request user, that user is added to both permissionsets."""
        user = superuser_client.user

        # Create a new EventCategory via API (this will naturally set up the request context)
        url = reverse("event-categories")
        data = {"value": "test-category", "display": "Test Category", "flag": "user"}
        response = superuser_client.post(url, data=data, format="json")

        assert response.status_code == 201
        category_id = response.data["id"]
        category = EventCategory.objects.get(id=category_id)

        # Get the permissionsets
        permissionset = PermissionSet.objects.get(name=category.auto_permissionset_name)
        geo_permissionset = PermissionSet.objects.get(name=category.auto_geographic_permission_set_name)

        # Verify the user was added to both permissionsets
        assert user in permissionset.user_set.all()
        assert user in geo_permissionset.user_set.all()

    def test_new_category_without_request_user_does_not_add_user(self):
        """Test that when a new EventCategory is created without a request user, no user is added."""
        # Ensure no request context
        original_request = getattr(request_context, "request", None)
        request_context.request = None

        try:
            # Create a new EventCategory
            category = EventCategory.objects.create(value="test-category-2", display="Test Category 2", flag="user")

            # Get the permissionsets
            permissionset = PermissionSet.objects.get(name=category.auto_permissionset_name)
            geo_permissionset = PermissionSet.objects.get(name=category.auto_geographic_permission_set_name)

            # Verify no users were added to the permissionsets
            assert permissionset.user_set.count() == 0
            assert geo_permissionset.user_set.count() == 0
        finally:
            # Restore the original request context
            request_context.request = original_request

    def test_value_change_updates_permission_codenames(self):
        """Changing value renames existing permission codenames to match the new value."""
        category = EventCategory.objects.create(value="old-type", display="Old Type", flag="user")
        permission_set = PermissionSet.objects.get(name=category.auto_permissionset_name)
        old_codenames = set(permission_set.permissions.values_list("codename", flat=True))
        assert old_codenames, "Expected permissions to exist before rename"
        assert all("old-type" in c for c in old_codenames)

        category.value = "new-type"
        category.save()

        permission_set.refresh_from_db()
        new_codenames = set(permission_set.permissions.values_list("codename", flat=True))
        assert all("new-type" in c for c in new_codenames), f"Expected new-type in codenames, got {new_codenames}"
        assert not old_codenames & new_codenames, "Old codenames should have been replaced"

    def test_value_change_updates_geo_permission_codenames(self):
        """Changing value also renames geographic permission codenames."""
        category = EventCategory.objects.create(value="old-geo", display="Old Geo", flag="user")
        geo_set = PermissionSet.objects.get(name=category.auto_geographic_permission_set_name)
        old_codenames = set(geo_set.permissions.values_list("codename", flat=True))
        assert old_codenames, "Expected geo permissions to exist before rename"
        assert all("old-geo" in c for c in old_codenames)

        category.value = "new-geo"
        category.save()

        geo_set.refresh_from_db()
        new_codenames = set(geo_set.permissions.values_list("codename", flat=True))
        assert all("new-geo" in c for c in new_codenames), f"Expected new-geo in codenames, got {new_codenames}"
        assert not old_codenames & new_codenames, "Old geo codenames should have been replaced"

    def test_value_and_display_change_updates_permissionsets_and_codenames(self):
        """Changing value and display together renames permission sets and permission codenames."""
        category = EventCategory.objects.create(value="old-type", display="Old Type", flag="user")
        old_permission_set_name = category.auto_permissionset_name
        old_geo_permission_set_name = category.auto_geographic_permission_set_name
        permission_set = PermissionSet.objects.get(name=old_permission_set_name)
        geo_permission_set = PermissionSet.objects.get(name=old_geo_permission_set_name)
        old_codenames = set(permission_set.permissions.values_list("codename", flat=True))
        old_geo_codenames = set(geo_permission_set.permissions.values_list("codename", flat=True))
        assert old_codenames, "Expected permissions to exist before rename"
        assert old_geo_codenames, "Expected geo permissions to exist before rename"

        category.value = "new-type"
        category.display = "New Type"
        category.save()

        new_permission_set_name = category.auto_permissionset_name
        new_geo_permission_set_name = category.auto_geographic_permission_set_name

        assert not PermissionSet.objects.filter(name=old_permission_set_name).exists()
        assert not PermissionSet.objects.filter(name=old_geo_permission_set_name).exists()

        permission_set = PermissionSet.objects.get(name=new_permission_set_name)
        geo_permission_set = PermissionSet.objects.get(name=new_geo_permission_set_name)

        new_codenames = set(permission_set.permissions.values_list("codename", flat=True))
        new_geo_codenames = set(geo_permission_set.permissions.values_list("codename", flat=True))

        assert all("new-type" in c for c in new_codenames), f"Expected new-type in codenames, got {new_codenames}"
        assert all(
            "new-type" in c for c in new_geo_codenames
        ), f"Expected new-type in geo codenames, got {new_geo_codenames}"
        assert not old_codenames & new_codenames, "Old permission codenames should have been replaced"
        assert (
            not old_geo_codenames & new_geo_codenames
        ), "Old geographic permission codenames should have been replaced"

    def test_display_only_change_does_not_alter_permission_codenames(self):
        """Changing only display leaves permission codenames unchanged."""
        category = EventCategory.objects.create(value="stable-value", display="Original", flag="user")
        permission_set = PermissionSet.objects.get(name=category.auto_permissionset_name)
        original_codenames = set(permission_set.permissions.values_list("codename", flat=True))

        category.display = "Updated Display"
        category.save()

        permission_set.refresh_from_db()
        assert set(permission_set.permissions.values_list("codename", flat=True)) == original_codenames

    def test_existing_category_update_does_not_add_user(self, superuser_client):
        """Test that when an existing EventCategory is updated via API, no user is added even if there's a request user."""

        # Create a category first (without request user - direct DB creation)
        original_request = getattr(request_context, "request", None)
        request_context.request = None
        category = EventCategory.objects.create(value="test-category-3", display="Test Category 3", flag="user")
        request_context.request = original_request

        # Get the permissionsets before update
        permissionset = PermissionSet.objects.get(name=category.auto_permissionset_name)
        geo_permissionset = PermissionSet.objects.get(name=category.auto_geographic_permission_set_name)
        initial_user_count = permissionset.user_set.count()
        initial_geo_user_count = geo_permissionset.user_set.count()

        # Update the existing category via API
        url = reverse("event-category", kwargs={"eventcategory_id": str(category.id)})
        data = {"display": "Updated Display"}
        response = superuser_client.patch(url, data=data, format="json")

        assert response.status_code == 200

        # Refresh permissionsets from DB
        permissionset.refresh_from_db()
        geo_permissionset.refresh_from_db()

        # Verify no users were added (since the permissionsets already existed)
        assert permissionset.user_set.count() == initial_user_count
        assert geo_permissionset.user_set.count() == initial_geo_user_count
