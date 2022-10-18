from django.conf import settings
from django.test import override_settings

from utils.tenant.builder import DjangoSettingsTenantBuilder


class TestTenantSettingsLoadedFromDjango:
    @override_settings(
        ACCEPT_EULA="false",
        ALERTS_RACE_LIMIT="20",
        DEFAULT_EVENT_FILTER_FROM_DAYS="30",
        GEO_PERMISSION_BAN_DURATON_MIN="15",
        GEO_PERMISSION_RADIUS_METERS="1",
        GEO_PERMISSION_SPEED_KM_H="10",
        PATROL_ENABLED="1",
        SERVER_FQDN="test.pamdas.org",
        SHOW_STATIONARY_SUBJECTS_ON_MAP="1",
        SHOW_TRACK_DAYS="44",
        SUBJECT_REGION_ENABLED="0",
        TABLEAU_DEFAULT_DASHBOARD="dashboard.tableau.org",
        TABLEAU_SITE_ID="test-site-id",
        TRACK_LENGTH="2",
    )
    def test_django_settings_load_successfully(self):
        tenant_settings = DjangoSettingsTenantBuilder.__wrapped__().build()

        assert tenant_settings.env_settings.accept_eula is False
        assert tenant_settings.env_settings.alert_rate_limit is 20
        assert tenant_settings.env_settings.default_event_filter_from_days is 30
        assert tenant_settings.env_settings.geo_permission_violation_ban_duration_min is 15
        assert tenant_settings.env_settings.geo_permission_radius_meters is 1
        assert tenant_settings.env_settings.geo_permission_speed_km_h is 10
        assert tenant_settings.env_settings.patrol_enabled is True
        assert tenant_settings.env_settings.fqdn is "test.pamdas.org"
        assert tenant_settings.env_settings.show_stationary_subjects_on_map is True
        assert tenant_settings.env_settings.show_track_days is 44
        assert tenant_settings.env_settings.subject_region_enabled is False
        assert tenant_settings.env_settings.tableau_default_dashboard is "dashboard.tableau.org"
        assert tenant_settings.env_settings.tableau_site_id is "test-site-id"
        assert tenant_settings.env_settings.track_length is 2

    @override_settings(ALERTS_ENABLED="1", DAILY_REPORT_ENABLED="1", EXPORT_KML_ENABLED="1", TABLEAU_ENABLED="1")
    def test_django_feature_flags_load_successfully(self):
        tenant_settings = DjangoSettingsTenantBuilder.__wrapped__().build()

        assert tenant_settings.feature_flags.alerts_enabled is True
        assert tenant_settings.feature_flags.daily_report_enabled is True
        assert tenant_settings.feature_flags.kml_export is True
        assert tenant_settings.feature_flags.tableau_enabled is True

    def test_django_settings_load_successfully_with_missing_optional_settings(self, monkeypatch):
        with override_settings():
            monkeypatch.delattr(settings, "DEFAULT_EVENT_FILTER_FROM_DAYS")
            monkeypatch.delattr(settings, "SHOW_STATIONARY_SUBJECTS_ON_MAP")
            monkeypatch.delattr(settings, "SHOW_TRACK_DAYS")
            monkeypatch.delattr(settings, "SUBJECT_REGION_ENABLED")

            tenant_settings = DjangoSettingsTenantBuilder.__wrapped__().build()

            assert tenant_settings.env_settings.default_event_filter_from_days is None
            assert tenant_settings.env_settings.show_stationary_subjects_on_map is True
            assert tenant_settings.env_settings.show_track_days is 16
            assert tenant_settings.env_settings.subject_region_enabled is True
