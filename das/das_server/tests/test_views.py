from unittest.mock import MagicMock, patch

import pytest

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from utils.tenant import Tenant
from utils.tenant.preview_features import PREVIEW_FEATURES, PreviewFeature


def _without_global_override(name):
    """Re-register ``name`` with no global_override so the tenant value / default decides.

    Features that carry a ``global_override`` short-circuit the per-tenant lookup,
    which would make the status-endpoint assertions below pass without exercising
    the tenant-value / default path they are about.
    """
    return patch.dict(
        PREVIEW_FEATURES,
        {name: PreviewFeature(default=PREVIEW_FEATURES[name].default, global_override=None)},
    )


@pytest.mark.django_db
class TestStatusView:
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_from_view_when_tms_is_turned_on(
        self, monkeypatch, superuser_client, tenant_response, tenant_document_cache_client_mock
    ):
        tenant_settings = Tenant.from_dict(tenant_response)
        tenant_settings.feature_flags.alerts_enabled = True
        tenant_settings.feature_flags.kml_export = True
        tenant_settings.feature_flags.events_enabled = True
        tenant_settings.feature_flags.subjects_enabled = True
        tenant_settings.feature_flags.spatial_features_enabled = True
        tenant_settings.feature_flags.analyzers_enabled = True
        tenant_settings.env_settings.patrol_enabled = True
        tenant_settings.env_settings.show_stationary_subjects_on_map = True
        monkeypatch.setattr("das_server.views.get_tenant_settings", MagicMock(return_value=tenant_settings))
        url = reverse("api-status")

        response = superuser_client.get(url)

        self._assert_feature_flags_response_match(response)

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_not_including_support_settings(
        self, monkeypatch, superuser_client, tenant_document_cache_client_mock
    ):
        monkeypatch.setattr("das_server.views.settings.EUS_SETTINGS", {"invalid": "settings"})
        url = reverse("api-status")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "eus_settings" not in response.data

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_including_support_settings(
        self, monkeypatch, superuser_client, tenant_document_cache_client_mock
    ):
        support_settings = {
            "email": "eus_test@pamdas.org",
            "name": "eus test user",
            "organization": "pamdas.org",
            "type": "email",
        }
        monkeypatch.setattr("das_server.views.settings.EUS_SETTINGS", support_settings)
        url = reverse("api-status")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["eus_settings"] == support_settings

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_with_db_connections_param(
        self, monkeypatch, superuser_client, tenant_document_cache_client_mock
    ):
        cursor_mock = MagicMock()
        cursor_mock.fetchone.return_value = [5]
        connection_mock = MagicMock()
        connection_mock.cursor.return_value.__enter__.return_value = cursor_mock
        migration_mock = MagicMock()
        migration_mock.app = "usercontent"
        migration_mock.name = "001_alter_db"
        monkeypatch.setattr("das_server.views.connection", connection_mock)
        monkeypatch.setattr("das_server.views.StatusView.get_last_migration", MagicMock(return_value=migration_mock))
        url = reverse("api-status")

        response = superuser_client.get(url, {"db_connections": True})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["db_connection_count"] == 5
        assert response.data["last_migration_app"] == "usercontent"
        assert response.data["last_migration_name"] == "001_alter_db"

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_with_service_status_param(
        self, monkeypatch, superuser_client, tenant_document_cache_client_mock
    ):
        utils_mock = MagicMock()
        utils_mock.get_source_provider_statuses.return_value = []
        monkeypatch.setattr("das_server.views.servicesutils", utils_mock)
        url = reverse("api-status")

        response = superuser_client.get(url, {"service_status": True})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["services"] == []

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_with_idp_required(self, monkeypatch, tenant_response, tenant_document_cache_client_mock):
        tenant_settings = Tenant.from_dict(tenant_response)
        tenant_settings.feature_flags.require_idp = True
        tenant_settings.feature_flags.idp_org_id = "some-org"
        monkeypatch.setattr("das_server.views.get_tenant_settings", MagicMock(return_value=tenant_settings))
        monkeypatch.setattr("accounts.backends.get_tenant_settings", MagicMock(return_value=tenant_settings))
        url = reverse("api-status")

        client = APIClient()
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_includes_dwh_settings(self, monkeypatch, superuser_client, tenant_document_cache_client_mock):
        monkeypatch.setattr("das_server.views.settings.DWH_API_URL", "https://warehouse-api.example.com")
        url = reverse("api-status")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["dwh_settings"] == {"api_url": "https://warehouse-api.example.com"}

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_dwh_settings_empty_when_not_configured(
        self, monkeypatch, superuser_client, tenant_document_cache_client_mock
    ):
        monkeypatch.setattr("das_server.views.settings.DWH_API_URL", "")
        url = reverse("api-status")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["dwh_settings"] == {"api_url": ""}

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_includes_enabled_preview_features(
        self, monkeypatch, superuser_client, tenant_response, tenant_document_cache_client_mock
    ):
        tenant_settings = Tenant.from_dict(tenant_response)
        tenant_settings.preview_features = {"community_input_admin_enabled": True}
        get_tenant_settings_mock = MagicMock(return_value=tenant_settings)
        monkeypatch.setattr("das_server.views.get_tenant_settings", get_tenant_settings_mock)
        monkeypatch.setattr("utils.tenant.preview_features.get_tenant_settings", get_tenant_settings_mock)
        url = reverse("api-status")

        with _without_global_override("community_input_admin_enabled"):
            response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["preview_features"]["community_input_admin_enabled"] is True

    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_get_status_preview_features_default_when_unset(
        self, monkeypatch, superuser_client, tenant_response, tenant_document_cache_client_mock
    ):
        tenant_settings = Tenant.from_dict(tenant_response)
        get_tenant_settings_mock = MagicMock(return_value=tenant_settings)
        monkeypatch.setattr("das_server.views.get_tenant_settings", get_tenant_settings_mock)
        monkeypatch.setattr("utils.tenant.preview_features.get_tenant_settings", get_tenant_settings_mock)
        url = reverse("api-status")

        with _without_global_override("community_input_admin_enabled"):
            response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "community_input_admin_enabled" in response.data["preview_features"]
        assert response.data["preview_features"]["community_input_admin_enabled"] is False

    def _assert_feature_flags_response_match(self, response):
        assert response.status_code == status.HTTP_200_OK
        assert response.data["event_matrix_enabled"] is False
        assert response.data["event_search_enabled"] is True
        assert response.data["export_kml_enabled"] is True
        assert response.data["daily_report_enabled"] is False
        assert response.data["alerts_enabled"] is True
        assert response.data["tableau_enabled"] is False
        assert response.data["eula_enabled"] is False
        assert response.data["events_enabled"] is True
        assert response.data["subjects_enabled"] is True
        assert response.data["spatial_features_enabled"] is True
        assert response.data["analyzers_enabled"] is True
        assert response.data["require_idp"] is False
        assert response.data["idp_org_id"] is None
