"""Tests for PatrolType CRUD API endpoints."""

from __future__ import annotations

import uuid

import pytest

from django.contrib.auth.models import Permission
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.validators import UniqueValidator

from activity.models import PatrolType
from core.models import DASTenant
from factories import PatrolTypeFactory, PermissionSetFactory
from utils.tenant.managers import UnsetDASTenantContextManager
from utils.tests_tools import API_BASE

PATROL_TYPES_URL = f"{API_BASE}/activity/patrols/types/"


def _detail_url(patrol_type_id: uuid.UUID | str) -> str:
    return f"{PATROL_TYPES_URL}{patrol_type_id}/"


class TestUrlResolving:
    @pytest.mark.django_db
    def test_patrol_types_list_url_resolves(self) -> None:
        url = reverse("patrol-types")
        assert url is not None

    @pytest.mark.django_db
    def test_patrol_type_detail_url_resolves(self) -> None:
        pt = PatrolTypeFactory.create()
        url = reverse("patrol-type", kwargs={"id": str(pt.id)})
        assert url is not None


class TestPatrolTypeCRUD:
    @pytest.mark.django_db
    def test_list_returns_patrol_types(self, superuser_client, patrol_type) -> None:
        response = superuser_client.get(PATROL_TYPES_URL)
        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.data]
        assert str(patrol_type.id) in ids

    @pytest.mark.django_db
    def test_retrieve_returns_single_patrol_type(self, superuser_client, patrol_type) -> None:
        response = superuser_client.get(_detail_url(patrol_type.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(patrol_type.id)
        assert response.data["value"] == patrol_type.value

    @pytest.mark.django_db
    def test_create_patrol_type(self, superuser_client) -> None:
        payload = {"value": "new_patrol_type", "display": "New Patrol Type"}
        response = superuser_client.post(PATROL_TYPES_URL, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["value"] == "new_patrol_type"
        assert response.data["display"] == "New Patrol Type"
        assert PatrolType.objects.filter(value="new_patrol_type").exists()

    @pytest.mark.django_db
    def test_create_with_icon_returns_matching_icon_id(self, superuser_client) -> None:
        payload = {"value": "icon_test_type", "display": "Icon Test", "icon": "my_custom_icon"}
        response = superuser_client.post(PATROL_TYPES_URL, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["icon"] == "my_custom_icon"
        assert response.data["icon_id"] == "my_custom_icon"

    @pytest.mark.django_db
    def test_partial_update_patrol_type(self, superuser_client, patrol_type) -> None:
        response = superuser_client.patch(
            _detail_url(patrol_type.id),
            data={"display": "Updated Display"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["display"] == "Updated Display"
        patrol_type.refresh_from_db()
        assert patrol_type.display == "Updated Display"

    @pytest.mark.django_db
    def test_update_patrol_type(self, superuser_client, patrol_type) -> None:
        payload = {
            "value": patrol_type.value,
            "display": "Fully Updated",
            "is_active": False,
        }
        response = superuser_client.put(
            _detail_url(patrol_type.id),
            data=payload,
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["display"] == "Fully Updated"
        assert response.data["is_active"] is False

    @pytest.mark.django_db
    def test_delete_patrol_type(self, superuser_client, patrol_type) -> None:
        pt_id = patrol_type.id
        response = superuser_client.delete(_detail_url(pt_id))
        # ExtendedJSONRenderer converts 204 → 200 with a data/status envelope.
        assert response.status_code == status.HTTP_200_OK
        assert not PatrolType.objects.filter(id=pt_id).exists()

    @pytest.mark.django_db
    def test_retrieve_returns_404_for_unknown_id(self, superuser_client) -> None:
        response = superuser_client.get(_detail_url(uuid.uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_unauthenticated_list_returns_403(self, client) -> None:
        response = client.get(PATROL_TYPES_URL)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    @pytest.mark.django_db
    def test_list_response_is_a_flat_list(self, superuser_client) -> None:
        PatrolTypeFactory.create_batch(3)
        response = superuser_client.get(PATROL_TYPES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    @pytest.mark.django_db
    def test_create_duplicate_value_returns_400(self, superuser_client, patrol_type) -> None:
        payload = {"value": patrol_type.value, "display": "Duplicate"}
        response = superuser_client.post(PATROL_TYPES_URL, data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_put_without_optional_fields_does_not_affect_required_ones(self, superuser_client, patrol_type) -> None:
        payload = {"value": patrol_type.value, "display": "PUT Updated"}
        response = superuser_client.put(_detail_url(patrol_type.id), data=payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["display"] == "PUT Updated"
        assert response.data["value"] == patrol_type.value

    @pytest.mark.django_db
    def test_db_unique_constraint_violation_returns_400(self, superuser_client, patrol_type, monkeypatch) -> None:
        # Disable the serializer-level UniqueValidator so a duplicate value passes
        # validation and the DB unique constraint fires inside create(), exercising
        # the _VALUE_CONSTRAINT branch of _handle_integrity_error.
        monkeypatch.setattr(UniqueValidator, "__call__", lambda self, value, serializer_field: None)

        payload = {"value": patrol_type.value, "display": "Duplicate via DB"}
        response = superuser_client.post(PATROL_TYPES_URL, data=payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" in response.data


class TestPatrolTypePermissions:
    @pytest.mark.django_db
    def test_user_without_add_perm_cannot_create(self, user_client) -> None:
        payload = {"value": "should_fail", "display": "Should Fail"}
        response = user_client.post(PATROL_TYPES_URL, data=payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_user_without_change_perm_cannot_patch(self, user_client, patrol_type) -> None:
        response = user_client.patch(
            _detail_url(patrol_type.id),
            data={"display": "No Access"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_user_without_delete_perm_cannot_delete(self, user_client, patrol_type) -> None:
        response = user_client.delete(_detail_url(patrol_type.id))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.fixture
    def read_only_user_client(self, user_client):
        """A user_client whose only granted permission is view_patroltype."""
        permission_set = PermissionSetFactory.create(
            das_tenant=user_client.user.das_tenant,
            permissions=[Permission.objects.get_by_natural_key("view_patroltype", "activity", "patroltype")],
        )
        user_client.user.permission_sets.add(permission_set)
        return user_client

    @pytest.mark.django_db
    def test_read_only_user_can_list(self, read_only_user_client, patrol_type) -> None:
        response = read_only_user_client.get(PATROL_TYPES_URL)
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_read_only_user_cannot_create(self, read_only_user_client) -> None:
        payload = {"value": "read_only_create", "display": "Read Only Create"}
        response = read_only_user_client.post(PATROL_TYPES_URL, data=payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_read_only_user_cannot_patch(self, read_only_user_client, patrol_type) -> None:
        response = read_only_user_client.patch(
            _detail_url(patrol_type.id),
            data={"display": "Read Only Patch"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_read_only_user_cannot_delete(self, read_only_user_client, patrol_type) -> None:
        response = read_only_user_client.delete(_detail_url(patrol_type.id))
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestPatrolTypeTenantIsolation:
    @pytest.mark.django_db
    def test_other_tenant_types_are_not_visible(self, superuser_client, das_tenant) -> None:
        other_tenant = DASTenant.objects.create(id=uuid.uuid4(), domain="other-patrol-type-isolation.example.com")
        other_pt = PatrolType(value="other_tenant_type", display="Other Tenant Type", das_tenant=other_tenant)
        other_pt.save()
        own_pt = PatrolType(value="own_tenant_type", display="Own Tenant Type", das_tenant=das_tenant)
        own_pt.save()

        response = superuser_client.get(PATROL_TYPES_URL)

        assert response.status_code == status.HTTP_200_OK
        values = [item["value"] for item in response.data]
        assert own_pt.value in values
        assert other_pt.value not in values

    @pytest.mark.django_db
    def test_same_value_in_different_tenant_is_allowed(self, superuser_client, das_tenant) -> None:
        other_tenant = DASTenant.objects.create(id=uuid.uuid4(), domain="other-patrol-type-cross.example.com")
        PatrolType.objects.create(value="shared_value", display="In Other Tenant", das_tenant=other_tenant)

        response = superuser_client.post(
            PATROL_TYPES_URL, data={"value": "shared_value", "display": "In Own Tenant"}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED

    @pytest.fixture
    def other_tenant_patrol_type(self, das_tenant):
        other_tenant = DASTenant.objects.create(id=uuid.uuid4(), domain="other-patrol-type-detail.example.com")
        pt = PatrolType(value="other_tenant_detail", display="Other Tenant Detail", das_tenant=other_tenant)
        pt.save()
        return pt

    @pytest.mark.django_db
    def test_retrieve_other_tenant_type_returns_404(self, superuser_client, other_tenant_patrol_type) -> None:
        response = superuser_client.get(_detail_url(other_tenant_patrol_type.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_patch_other_tenant_type_returns_404(self, superuser_client, other_tenant_patrol_type) -> None:
        response = superuser_client.patch(
            _detail_url(other_tenant_patrol_type.id),
            data={"display": "Cross Tenant Patch"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_delete_other_tenant_type_returns_404(self, superuser_client, other_tenant_patrol_type) -> None:
        response = superuser_client.delete(_detail_url(other_tenant_patrol_type.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        with UnsetDASTenantContextManager():
            assert PatrolType.objects.filter(id=other_tenant_patrol_type.id).exists()
