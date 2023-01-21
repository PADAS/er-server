from unittest.mock import MagicMock

import pytest

from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from utils.features import features
from utils.tenant import Tenant


@pytest.mark.django_db
class TestStatusView:
    @override_settings(EXPORT_KML_ENABLED=True)
    @override_settings(SHOW_STATIONARY_SUBJECTS_ON_MAP=True)
    @pytest.mark.skipif(features.tms.is_on(), reason="TMS feature flag is on")
    def test_get_status_from_view_when_tms_is_turned_off(self, superuser_client):
        url = reverse("api-status")

        response = superuser_client.get(url)

        self._assert_feature_flags_response_match(response)

    @pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
    def test_get_status_from_view_when_tms_is_turned_on(self, monkeypatch, superuser_client, tenant_response):
        tenant_settings = Tenant.from_dict(tenant_response)
        tenant_settings.feature_flags.alerts_enabled = True
        tenant_settings.feature_flags.patrol_enabled = True
        tenant_settings.feature_flags.kml_export = True
        tenant_settings.feature_flags.show_stationary_subjects_on_map = True
        monkeypatch.setattr("das_server.views.get_tenant_settings", MagicMock(return_value=tenant_settings))
        url = reverse("api-status")

        response = superuser_client.get(url)

        self._assert_feature_flags_response_match(response)

    def test_get_status_not_including_support_settings(self, monkeypatch, superuser_client):
        monkeypatch.setattr("das_server.views.settings.EUS_SETTINGS", {"invalid": "settings"})
        url = reverse("api-status")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "eus_settings" not in response.data

    def test_get_status_including_support_settings(self, monkeypatch, superuser_client):
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

    def test_get_status_with_db_connections_param(self, monkeypatch, superuser_client):
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

    def test_get_status_with_service_status_param(self, monkeypatch, superuser_client):
        utils_mock = MagicMock()
        utils_mock.get_source_provider_statuses.return_value = []
        monkeypatch.setattr("das_server.views.servicesutils", utils_mock)
        url = reverse("api-status")

        response = superuser_client.get(url, {"service_status": True})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["services"] == []

    def _assert_feature_flags_response_match(self, response):
        assert response.status_code == status.HTTP_200_OK
        assert response.data["event_matrix_enabled"] is False
        assert response.data["event_search_enabled"] is True
        assert response.data["export_kml_enabled"] is True
        assert response.data["show_stationary_subjects_on_map"] is True
        assert response.data["daily_report_enabled"] is False
        assert response.data["alerts_enabled"] is True
        assert response.data["tableau_enabled"] is False
        assert response.data["eula_enabled"] is False
        assert response.data["patrol_enabled"] is True
