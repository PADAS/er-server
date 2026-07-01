"""Tests for analyzer config API endpoints (ViewSet-based)."""

from __future__ import annotations

import uuid

import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant

from django.contrib.auth.models import Permission
from rest_framework import status

from accounts.models import PermissionSet
from analyzers import views
from analyzers.models import (
    EnvironmentalSubjectAnalyzerConfig,
    FeatureProximityAnalyzerConfig,
    GeofenceAnalyzerConfig,
    ImmobilityAnalyzerConfig,
    LowSpeedPercentileAnalyzerConfig,
    LowSpeedWilcoxAnalyzerConfig,
    MovementClusterAnalyzerConfig,
    ObservationAttributeAnalyzerConfig,
    SubjectProximityAnalyzerConfig,
)
from core.models import DASTenant
from mapping.models import SpatialFeatureGroupStatic
from observations.models import SubjectGroup
from utils.tests_tools import API_BASE, is_url_resolved

ANALYZERS_BASE = f"{API_BASE}/analyzers"


@pytest.fixture
def subject_group(das_tenant):
    return SubjectGroup.objects.create(name="crud_test_group", das_tenant=das_tenant)


@pytest.fixture
def immobility_config(subject_group):
    return ImmobilityAnalyzerConfig.objects.create(
        name="test_immobility",
        subject_group=subject_group,
    )


@pytest.fixture
def other_tenant():
    return DASTenant.objects.create(id=uuid.uuid4(), domain="other-tenant-isolation.example.com")


@pytest.fixture
def other_immobility_config(other_tenant):
    other_sg = SubjectGroup.objects.create(name="other_tenant_group", das_tenant=other_tenant)
    config = ImmobilityAnalyzerConfig(
        name="other_tenant_immobility",
        subject_group=other_sg,
        das_tenant=other_tenant,
    )
    config.save()
    return config


@pytest.fixture
def other_tenant_feature_group(other_tenant):
    return SpatialFeatureGroupStatic.objects.create(name="other_tenant_feature_group", das_tenant=other_tenant)


@pytest.fixture
def view_only_immobility_client(create_user, create_client_for_user, das_tenant):
    """A non-superuser client granted ONLY view_immobilityanalyzerconfig via a PermissionSet."""
    user = create_user(das_tenant=das_tenant)
    permission = Permission.objects.get(
        content_type__app_label="analyzers",
        codename="view_immobilityanalyzerconfig",
    )
    perm_set = PermissionSet.objects.create(name="immobility_view_only", das_tenant=das_tenant)
    perm_set.permissions.add(permission)
    user.permission_sets.add(perm_set)
    return create_client_for_user(user)


class TestUrlResolving:
    @pytest.mark.parametrize(
        ("path", "viewset"),
        [
            ("analyzers/geofence/", views.GeofenceAnalyzerConfigViewSet),
            ("analyzers/featureproximity/", views.FeatureProximityAnalyzerConfigViewSet),
            ("analyzers/subjectproximity/", views.SubjectProximityAnalyzerConfigViewSet),
            ("analyzers/immobility/", views.ImmobilityAnalyzerConfigViewSet),
            ("analyzers/environmental/", views.EnvironmentalAnalyzerConfigViewSet),
            ("analyzers/lowspeedpercentile/", views.LowSpeedPercentileAnalyzerConfigViewSet),
            ("analyzers/lowspeedwilcox/", views.LowSpeedWilcoxAnalyzerConfigViewSet),
            ("analyzers/movementcluster/", views.MovementClusterAnalyzerConfigViewSet),
            ("analyzers/observationattribute/", views.ObservationAttributeAnalyzerConfigViewSet),
        ],
    )
    def test_list_url_resolves(self, path: str, viewset: type) -> None:
        assert is_url_resolved(api_path=path, view=viewset)


class TestImmobilityAnalyzerConfig:
    """CRUD tests using ImmobilityAnalyzerConfig as a representative type."""

    list_url = f"{ANALYZERS_BASE}/immobility/"

    def detail_url(self, pk: str) -> str:
        return f"{ANALYZERS_BASE}/immobility/{pk}/"

    @pytest.mark.django_db
    def test_list_returns_all_configs(self, superuser_client, immobility_config):
        response = superuser_client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.data["results"]]
        assert str(immobility_config.id) in ids

    @pytest.mark.django_db
    def test_list_filter_active(self, superuser_client, subject_group):
        active = ImmobilityAnalyzerConfig.objects.create(
            name="active_immobility", subject_group=subject_group, is_active=True
        )
        inactive = ImmobilityAnalyzerConfig.objects.create(
            name="inactive_immobility", subject_group=subject_group, is_active=False
        )

        response = superuser_client.get(self.list_url, {"active": "true"})
        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.data["results"]]
        assert str(active.id) in ids
        assert str(inactive.id) not in ids

        response = superuser_client.get(self.list_url, {"active": "false"})
        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.data["results"]]
        assert str(inactive.id) in ids
        assert str(active.id) not in ids

    @pytest.mark.django_db
    def test_retrieve_returns_config(self, superuser_client, immobility_config):
        response = superuser_client.get(self.detail_url(immobility_config.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(immobility_config.id)
        assert response.data["name"] == immobility_config.name
        assert response.data["analyzer_category"] == "immobility"

    @pytest.mark.django_db
    def test_create_config(self, superuser_client, subject_group):
        payload = {
            "name": "new_immobility_analyzer",
            "subject_group": subject_group.id,
            "threshold_radius": 20.0,
            "threshold_time": 7200,
            "threshold_probability": 0.75,
        }
        response = superuser_client.post(self.list_url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == payload["name"]
        assert response.data["analyzer_category"] == "immobility"
        assert ImmobilityAnalyzerConfig.objects.filter(name=payload["name"]).exists()

    @pytest.mark.django_db
    def test_create_without_schedule_defaults_to_empty_list(self, superuser_client, subject_group):
        # Exercises the mixin's schedule field with default=list: omitting the key
        # should succeed and produce an empty list rather than null.
        payload = {
            "name": "no_schedule_immobility",
            "subject_group": subject_group.id,
            "threshold_radius": 20.0,
            "threshold_time": 7200,
            "threshold_probability": 0.75,
        }
        response = superuser_client.post(self.list_url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["schedule"] == []
        config = ImmobilityAnalyzerConfig.objects.get(name=payload["name"])
        assert config.schedule == []

    @pytest.mark.django_db
    def test_analyzer_category_is_read_only_on_create(self, superuser_client, subject_group):
        # analyzer_category is read-only; a client-supplied value must be ignored
        # and the model's own category returned instead.
        payload = {
            "name": "read_only_category_immobility",
            "subject_group": subject_group.id,
            "threshold_radius": 20.0,
            "threshold_time": 7200,
            "threshold_probability": 0.75,
            "analyzer_category": "attempted_override",
        }
        response = superuser_client.post(self.list_url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["analyzer_category"] == "immobility"

    @pytest.mark.django_db
    def test_create_duplicate_name_race_returns_409(self, superuser_client, subject_group, monkeypatch):
        # Simulate the concurrent-insert race: bypass the validate_name pre-check so the
        # DB UniqueConstraint(das_tenant, name) trips and raises IntegrityError. The viewset
        # must translate that into a 409, not a 500.
        ImmobilityAnalyzerConfig.objects.create(
            name="dup_name_immobility",
            subject_group=subject_group,
        )
        from analyzers.serializers import _AnalyzerConfigMixin

        monkeypatch.setattr(_AnalyzerConfigMixin, "validate_name", lambda self, value: value)
        payload = {
            "name": "dup_name_immobility",
            "subject_group": subject_group.id,
            "threshold_radius": 20.0,
            "threshold_time": 7200,
            "threshold_probability": 0.75,
        }
        response = superuser_client.post(self.list_url, payload, format="json")
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_partial_update_config(self, superuser_client, immobility_config):
        response = superuser_client.patch(
            self.detail_url(immobility_config.id),
            {"threshold_radius": 99.0},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["threshold_radius"] == 99.0
        immobility_config.refresh_from_db()
        assert immobility_config.threshold_radius == 99.0

    @pytest.mark.django_db
    def test_delete_config(self, superuser_client, immobility_config):
        config_id = immobility_config.id
        response = superuser_client.delete(self.detail_url(config_id))
        assert response.status_code == status.HTTP_200_OK  # 204 converted to 200 by ExtendedJSONRenderer
        assert not ImmobilityAnalyzerConfig.objects.filter(id=config_id).exists()

    @pytest.mark.django_db
    def test_invalid_active_param_returns_400(self, superuser_client):
        response = superuser_client.get(self.list_url, {"active": "maybe"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_unauthenticated_request_is_rejected(self, anonymous_client, immobility_config):
        response = anonymous_client.get(self.list_url)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    @pytest.mark.django_db
    def test_user_without_view_permission_gets_forbidden(self, user_client):
        response = user_client.get(self.list_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    @pytest.mark.parametrize("method", ["post", "patch"])
    def test_unauthenticated_write_is_rejected(self, anonymous_client, method: str) -> None:
        response = getattr(anonymous_client, method)(self.list_url, data={}, format="json")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    @pytest.mark.django_db
    def test_unauthenticated_delete_is_rejected(self, anonymous_client, immobility_config) -> None:
        response = anonymous_client.delete(self.detail_url(immobility_config.id))
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    @pytest.mark.django_db
    @pytest.mark.parametrize("method", ["post", "patch"])
    def test_user_without_permissions_cannot_write(self, user_client, method: str) -> None:
        response = getattr(user_client, method)(self.list_url, data={}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_unauthenticated_request_with_bad_active_param_returns_401_or_403(self, anonymous_client) -> None:
        # The active-param validation must not run before the permission check: an
        # unauthenticated caller hitting a bad ?active= value should be rejected as
        # 401/403, not handed a 400.
        response = anonymous_client.get(self.list_url, {"active": "garbage"})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    @pytest.mark.django_db
    def test_unauthorized_user_with_bad_active_param_returns_403(self, user_client) -> None:
        # A user lacking view permission and passing a bad ?active= value should be
        # forbidden (403), not get a 400 from param validation running first.
        response = user_client.get(self.list_url, {"active": "garbage"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_view_only_user_can_get(self, view_only_immobility_client, immobility_config) -> None:
        list_response = view_only_immobility_client.get(self.list_url)
        assert list_response.status_code == status.HTTP_200_OK
        detail_response = view_only_immobility_client.get(self.detail_url(immobility_config.id))
        assert detail_response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_view_only_user_cannot_create(self, view_only_immobility_client, subject_group) -> None:
        response = view_only_immobility_client.post(
            self.list_url,
            {"name": "view_only_attempt", "subject_group": str(subject_group.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_view_only_user_cannot_patch(self, view_only_immobility_client, immobility_config) -> None:
        response = view_only_immobility_client.patch(
            self.detail_url(immobility_config.id),
            {"threshold_radius": 12.0},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.django_db
    def test_view_only_user_cannot_delete(self, view_only_immobility_client, immobility_config) -> None:
        response = view_only_immobility_client.delete(self.detail_url(immobility_config.id))
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestAllAnalyzerTypeListEndpoints:
    """Smoke-test that each type's list endpoint returns 200 for an authenticated user."""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("url_fragment", "model", "extra_fields"),
        [
            ("geofence", GeofenceAnalyzerConfig, {}),
            ("featureproximity", FeatureProximityAnalyzerConfig, {}),
            ("immobility", ImmobilityAnalyzerConfig, {}),
            (
                "environmental",
                EnvironmentalSubjectAnalyzerConfig,
                {"short_description": "smoke", "GEE_img_name": "img", "GEE_img_band_name": "b1"},
            ),
            ("lowspeedpercentile", LowSpeedPercentileAnalyzerConfig, {}),
            ("lowspeedwilcox", LowSpeedWilcoxAnalyzerConfig, {}),
            ("movementcluster", MovementClusterAnalyzerConfig, {}),
            (
                "observationattribute",
                ObservationAttributeAnalyzerConfig,
                {
                    "attribute_name": "speed",
                    "aggregation": "mean",
                    "comparator": ">",
                    "warning_value": 5.0,
                    "critical_value": 10.0,
                },
            ),
        ],
    )
    def test_list_returns_200(
        self,
        superuser_client,
        subject_group,
        url_fragment: str,
        model: type,
        extra_fields: dict,
    ) -> None:
        model.objects.create(
            name=f"smoke_{url_fragment}",
            subject_group=subject_group,
            **extra_fields,
        )
        response = superuser_client.get(f"{ANALYZERS_BASE}/{url_fragment}/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

    @pytest.mark.django_db
    def test_subject_proximity_list_returns_200(self, superuser_client, subject_group, das_tenant):
        second_group = SubjectGroup.objects.create(name="crud_test_group_2", das_tenant=das_tenant)
        SubjectProximityAnalyzerConfig.objects.create(
            name="smoke_subjectproximity",
            subject_group=subject_group,
            second_subject_group=second_group,
        )
        response = superuser_client.get(f"{ANALYZERS_BASE}/subjectproximity/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1


class TestTenantIsolation:
    """Verify that list endpoints never expose another tenant's configs."""

    list_url = f"{ANALYZERS_BASE}/immobility/"

    @pytest.mark.django_db
    def test_other_tenant_configs_are_not_visible(
        self,
        superuser_client,
        das_tenant,
        subject_group,
        other_immobility_config,
    ) -> None:
        # Set das_tenant as the active tenant so the ORM manager filters to it.
        previous_tenant = get_current_tenant()
        set_current_tenant(das_tenant)
        try:
            own_config = ImmobilityAnalyzerConfig.objects.create(
                name="own_tenant_config",
                subject_group=subject_group,
            )
            response = superuser_client.get(self.list_url)
        finally:
            set_current_tenant(previous_tenant)

        assert response.status_code == status.HTTP_200_OK
        names = [item["name"] for item in response.data["results"]]
        assert own_config.name in names
        assert other_immobility_config.name not in names

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("method", "body"),
        [
            ("get", {}),
            ("patch", {"threshold_radius": 999.0}),
            ("delete", {}),
        ],
    )
    def test_other_tenant_config_detail_returns_404(
        self,
        superuser_client,
        das_tenant,
        other_immobility_config,
        method: str,
        body: dict,
    ) -> None:
        url = f"{ANALYZERS_BASE}/immobility/{other_immobility_config.id}/"
        previous_tenant = get_current_tenant()
        set_current_tenant(das_tenant)
        try:
            response = getattr(superuser_client, method)(url, body, format="json")
        finally:
            set_current_tenant(previous_tenant)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_create_with_other_tenant_subject_group_returns_400(
        self,
        superuser_client,
        das_tenant,
        other_tenant,
    ) -> None:
        # SubjectGroup.objects uses TenantManagerMixin, so a PK from another tenant
        # won't be found by DRF's PrimaryKeyRelatedField validation.
        other_sg = SubjectGroup.objects.create(name="cross_tenant_sg", das_tenant=other_tenant)

        previous_tenant = get_current_tenant()
        set_current_tenant(das_tenant)
        try:
            response = superuser_client.post(
                self.list_url,
                {"name": "cross_tenant_create", "subject_group": str(other_sg.id)},
                format="json",
            )
        finally:
            set_current_tenant(previous_tenant)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    @pytest.mark.parametrize("field", ["critical_geofence_group", "warning_geofence_group", "containment_regions"])
    def test_create_geofence_with_other_tenant_feature_group_returns_400(
        self,
        superuser_client,
        das_tenant,
        subject_group,
        other_tenant_feature_group,
        field: str,
    ) -> None:
        # critical_geofence_group / warning_geofence_group / containment_regions are plain
        # models.ForeignKey to SpatialFeatureGroupStatic (NOT TenantForeignKey). Cross-tenant
        # isolation relies on SpatialFeatureGroupStatic.objects (CommonTenantManager) scoping
        # DRF's PrimaryKeyRelatedField queryset to the active tenant, so a PK belonging to
        # another tenant must fail validation with a 400.
        url = f"{ANALYZERS_BASE}/geofence/"
        previous_tenant = get_current_tenant()
        set_current_tenant(das_tenant)
        try:
            response = superuser_client.post(
                url,
                {
                    "name": "cross_tenant_geofence",
                    "subject_group": str(subject_group.id),
                    field: str(other_tenant_feature_group.id),
                },
                format="json",
            )
        finally:
            set_current_tenant(previous_tenant)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert field in response.data

    @pytest.mark.django_db
    def test_create_feature_proximity_with_other_tenant_feature_group_returns_400(
        self,
        superuser_client,
        das_tenant,
        subject_group,
        other_tenant_feature_group,
    ) -> None:
        # proximal_features is a plain models.ForeignKey to SpatialFeatureGroupStatic
        # (NOT TenantForeignKey); a PK from another tenant must fail validation with a 400.
        url = f"{ANALYZERS_BASE}/featureproximity/"
        previous_tenant = get_current_tenant()
        set_current_tenant(das_tenant)
        try:
            response = superuser_client.post(
                url,
                {
                    "name": "cross_tenant_feature_proximity",
                    "subject_group": str(subject_group.id),
                    "proximal_features": str(other_tenant_feature_group.id),
                },
                format="json",
            )
        finally:
            set_current_tenant(previous_tenant)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "proximal_features" in response.data


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestProximityThresholdValidation:
    """Verify that threshold_dist_meters must be strictly > 0 on both proximity analyzer types."""

    feature_proximity_url = f"{ANALYZERS_BASE}/featureproximity/"
    subject_proximity_url = f"{ANALYZERS_BASE}/subjectproximity/"

    @pytest.fixture
    def proximal_feature_group(self, das_tenant):
        return SpatialFeatureGroupStatic.objects.create(name="test_feature_group", das_tenant=das_tenant)

    @pytest.fixture
    def second_subject_group(self, das_tenant):
        return SubjectGroup.objects.create(name="second_group", das_tenant=das_tenant)

    # --- FeatureProximityAnalyzerConfig ---

    @pytest.mark.parametrize("bad_value", [0, -1, -100.5])
    def test_feature_proximity_rejects_non_positive_threshold(
        self, superuser_client, subject_group, proximal_feature_group, bad_value: float
    ) -> None:
        payload = {
            "name": f"fp_bad_threshold_{bad_value}",
            "subject_group": subject_group.id,
            "proximal_features": proximal_feature_group.id,
            "threshold_dist_meters": bad_value,
        }
        response = superuser_client.post(self.feature_proximity_url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "threshold_dist_meters" in response.data

    def test_feature_proximity_accepts_positive_threshold(
        self, superuser_client, subject_group, proximal_feature_group
    ) -> None:
        payload = {
            "name": "fp_valid_threshold",
            "subject_group": subject_group.id,
            "proximal_features": proximal_feature_group.id,
            "threshold_dist_meters": 500.0,
        }
        response = superuser_client.post(self.feature_proximity_url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["threshold_dist_meters"] == 500.0

    # --- SubjectProximityAnalyzerConfig ---

    @pytest.mark.parametrize("bad_value", [0, -1, -100.5])
    def test_subject_proximity_rejects_non_positive_threshold(
        self, superuser_client, subject_group, second_subject_group, bad_value: float
    ) -> None:
        payload = {
            "name": f"sp_bad_threshold_{bad_value}",
            "subject_group": subject_group.id,
            "second_subject_group": second_subject_group.id,
            "threshold_dist_meters": bad_value,
        }
        response = superuser_client.post(self.subject_proximity_url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "threshold_dist_meters" in response.data

    def test_subject_proximity_accepts_positive_threshold(
        self, superuser_client, subject_group, second_subject_group
    ) -> None:
        payload = {
            "name": "sp_valid_threshold",
            "subject_group": subject_group.id,
            "second_subject_group": second_subject_group.id,
            "threshold_dist_meters": 100.0,
        }
        response = superuser_client.post(self.subject_proximity_url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["threshold_dist_meters"] == 100.0
