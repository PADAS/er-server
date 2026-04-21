import uuid

import pytest

from django.contrib.auth.models import Permission
from django.urls import reverse

from accounts.models import PermissionSet
from accounts.utils import add_tenant_to_permission_codename
from activity.models import Event
from factories import (
    EventCategoryFactory,
    EventFactory,
    EventTypeFactory,
    SubjectFactory,
)


@pytest.mark.usefixtures("tenant_settings", "das_tenant")
@pytest.mark.django_db
class TestEventBulkDeleteView:
    url = reverse("events-bulk-delete")

    def test_bulk_delete_success(self, superuser_client, five_events):
        ids = [str(e.id) for e in five_events]
        response = superuser_client.delete(self.url, {"ids": ids}, format="json")

        assert response.status_code == 200
        assert response.data["deleted"] == 5

    def test_bulk_delete_empty_ids(self, superuser_client):
        response = superuser_client.delete(self.url, {"ids": []}, format="json")

        assert response.status_code == 200
        assert response.data["deleted"] == 0

    def test_bulk_delete_invalid_payload(self, superuser_client):
        response = superuser_client.delete(self.url, {"ids": "not-a-list"}, format="json")

        assert response.status_code == 400

    def test_bulk_delete_nonexistent_ids_returns_403(self, superuser_client):
        fake_ids = [str(uuid.uuid4()) for _ in range(3)]
        response = superuser_client.delete(self.url, {"ids": fake_ids}, format="json")

        assert response.status_code == 403

    def test_bulk_delete_partial_access_returns_403_and_deletes_nothing(self, superuser_client, five_events):
        """Mixing accessible events with inaccessible IDs returns 403 and deletes nothing."""
        existing_ids = [str(five_events[0].id), str(five_events[1].id)]
        fake_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        all_ids = existing_ids + fake_ids

        response = superuser_client.delete(self.url, {"ids": all_ids}, format="json")

        assert response.status_code == 403
        assert Event.objects.filter(id__in=existing_ids).count() == 2

    def test_bulk_delete_unauthenticated(self, anonymous_client, five_events):
        ids = [str(e.id) for e in five_events]
        response = anonymous_client.delete(self.url, {"ids": ids}, format="json")

        assert response.status_code in (401, 403)

    def test_bulk_delete_no_permission_returns_403(self, create_client_for_user, create_user, das_tenant):
        """User with no delete permissions gets 403."""
        category = EventCategoryFactory.create(value="test_cat_nodelete", das_tenant=das_tenant)
        event_type = EventTypeFactory.create(category=category, das_tenant=das_tenant)
        events = EventFactory.create_batch(3, event_type=event_type, das_tenant=das_tenant)

        user = create_user()
        client = create_client_for_user(user)

        ids = [str(e.id) for e in events]
        response = client.delete(self.url, {"ids": ids}, format="json")

        assert response.status_code == 403

    @pytest.mark.usefixtures("das_tenant_monkeypatch")
    def test_bulk_delete_partial_category_permission_returns_403_and_deletes_nothing(
        self, create_client_for_user, create_user, das_tenant
    ):
        """User can delete events in cat_a but not cat_b; requesting both returns 403 and deletes nothing."""
        cat_a = EventCategoryFactory.create(value="test_cat_a", das_tenant=das_tenant)
        cat_b = EventCategoryFactory.create(value="test_cat_b", das_tenant=das_tenant)
        et_a = EventTypeFactory.create(category=cat_a, das_tenant=das_tenant)
        et_b = EventTypeFactory.create(category=cat_b, das_tenant=das_tenant)
        event_a = EventFactory.create(event_type=et_a, das_tenant=das_tenant)
        event_b = EventFactory.create(event_type=et_b, das_tenant=das_tenant)

        user = create_user()
        permission_set = PermissionSet.objects.create(name="test_cat_a_only_permset")
        delete_codename = add_tenant_to_permission_codename(das_tenant.id, f"{cat_a.value}_delete")
        delete_perm = Permission.objects.get(codename=delete_codename, content_type__app_label="activity")
        permission_set.permissions.add(delete_perm)
        user.permission_sets.add(permission_set)

        client = create_client_for_user(user)
        response = client.delete(self.url, {"ids": [str(event_a.id), str(event_b.id)]}, format="json")

        assert response.status_code == 403
        assert Event.objects.filter(id__in=[event_a.id, event_b.id]).count() == 2

    @pytest.mark.usefixtures("das_tenant_monkeypatch")
    def test_bulk_delete_with_full_permission(self, create_client_for_user, create_user, das_tenant):
        """User with delete permission for a category can delete all events in that category."""
        category = EventCategoryFactory.create(value="test_cat_delete", das_tenant=das_tenant)
        event_type = EventTypeFactory.create(category=category, das_tenant=das_tenant)
        events = EventFactory.create_batch(3, event_type=event_type, das_tenant=das_tenant)

        user = create_user()
        permission_set = PermissionSet.objects.create(name="test_delete_permset")
        delete_codename = add_tenant_to_permission_codename(das_tenant.id, f"{category.value}_delete")
        delete_perm = Permission.objects.get(codename=delete_codename, content_type__app_label="activity")
        permission_set.permissions.add(delete_perm)
        user.permission_sets.add(permission_set)

        client = create_client_for_user(user)
        ids = [str(e.id) for e in events]
        response = client.delete(self.url, {"ids": ids}, format="json")

        assert response.status_code == 200
        assert response.data["deleted"] == 3

    def test_bulk_delete_removes_events_from_db(self, superuser_client, five_events):
        ids = [str(e.id) for e in five_events]
        superuser_client.delete(self.url, {"ids": ids}, format="json")

        assert Event.objects.filter(id__in=ids).count() == 0

    def test_bulk_delete_invalid_uuid_strings_returns_400(self, superuser_client):
        """Non-UUID strings in ids list return 400 rather than a 500 DB error."""
        bad_ids = ["not-a-uuid", "also-bad", str(uuid.uuid4())]
        response = superuser_client.delete(self.url, {"ids": bad_ids}, format="json")

        assert response.status_code == 400

    @pytest.mark.usefixtures("das_tenant_monkeypatch")
    def test_bulk_delete_event_with_inaccessible_related_subject_returns_403(
        self, create_client_for_user, create_user, das_tenant
    ):
        """User with category delete permission is still denied if the event has a
        related subject outside their subject-group access."""
        category = EventCategoryFactory.create(value="test_cat_subj", das_tenant=das_tenant)
        event_type = EventTypeFactory.create(category=category, das_tenant=das_tenant)
        event = EventFactory.create(event_type=event_type, das_tenant=das_tenant)

        # Attach a subject the user will have no access to (not in any group)
        subject = SubjectFactory.create()
        event.related_subjects.add(subject)

        user = create_user()
        permission_set = PermissionSet.objects.create(name="test_subj_delete_permset")
        delete_codename = add_tenant_to_permission_codename(das_tenant.id, f"{category.value}_delete")
        delete_perm = Permission.objects.get(codename=delete_codename, content_type__app_label="activity")
        permission_set.permissions.add(delete_perm)
        user.permission_sets.add(permission_set)

        client = create_client_for_user(user)
        response = client.delete(self.url, {"ids": [str(event.id)]}, format="json")

        assert response.status_code == 403
        assert Event.objects.filter(id=event.id).exists()
