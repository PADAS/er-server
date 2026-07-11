"""Regression tests for the SpatialFeature Django admin change form (ERA-13369).

Renaming a bulk-imported SpatialFeature used to fail with HTTP 400 because the
editable OpenLayers geometry widget round-tripped the full WKT of dense
road-network MultiLineStrings back in the POST body, tripping
DATA_UPLOAD_MAX_MEMORY_SIZE (RequestDataTooBig) before the form was validated.

The fix makes ``feature_geometry`` read-only on the change view (rendered as a
lightweight summary) only when the geometry's vertex count exceeds
``settings.MAPPING_ADMIN_GEOMETRY_EDIT_MAX_VERTICES``. Smaller geometries — and
the add view, regardless of size — keep the ordinary editable OpenLayers widget.
"""

from __future__ import annotations

import pytest

from django.contrib.admin.sites import AdminSite
from django.contrib.gis.geos import LineString, MultiLineString
from django.test import override_settings
from django.urls import reverse

from mapping.admin import SpatialFeatureAdmin
from mapping.models import SpatialFeature, SpatialFeatureType


def _dense_multilinestring(num_lines: int = 250, points_per_line: int = 50) -> MultiLineString:
    """Build a realistic multi-point MultiLineString with many vertices.

    250 lines x 50 points = 12,500 vertices, comfortably above the default
    MAPPING_ADMIN_GEOMETRY_EDIT_MAX_VERTICES threshold of 10,000 so this fixture
    always exercises the read-only summary path.
    """
    lines = []
    for line_index in range(num_lines):
        base = line_index * 0.01
        coords = [(base + point_index * 0.0001, base + point_index * 0.0002) for point_index in range(points_per_line)]
        lines.append(LineString(coords, srid=4326))
    return MultiLineString(lines, srid=4326)


@pytest.fixture
def dense_feature(feature_type1: SpatialFeatureType) -> SpatialFeature:
    return SpatialFeature.objects.create(
        name="Imported Road Network",
        feature_type=feature_type1,
        feature_geometry=_dense_multilinestring(),
    )


def _inline_management_form_data(admin_instance: SpatialFeatureAdmin, request, obj: SpatialFeature) -> dict[str, str]:
    """Build empty management-form data for every inline on the change form."""
    data: dict[str, str] = {}
    for inline in admin_instance.get_inline_instances(request, obj):
        formset_class = inline.get_formset(request, obj)
        prefix = formset_class.get_default_prefix()
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": "0",
                f"{prefix}-INITIAL_FORMS": "0",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
            }
        )
    return data


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureAdminChangeForm:
    def test_rename_without_geometry_in_post_succeeds(self, superuser_client, dense_feature):
        """A name-only edit that omits feature_geometry saves and redirects (302)."""
        original_geometry = dense_feature.feature_geometry
        assert original_geometry.num_coords > 1000  # sanity check the fixture is dense

        admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
        request = superuser_client.get(
            reverse("admin:mapping_spatialfeature_change", args=(dense_feature.id,))
        ).wsgi_request

        # Simulate the fixed form: geometry is read-only, so the browser does NOT
        # send feature_geometry back.
        post_data = {
            "id": str(dense_feature.id),
            "name": "Renamed Road Network",
            "feature_type": str(dense_feature.feature_type_id),
            "spatialfile": "",
            "short_name": "",
            "description": "",
            "attributes": "{}",
            "provenance": "{}",
            "external_id": "",
            "external_source": "",
            "_save": "Save",
        }
        post_data.update(_inline_management_form_data(admin_instance, request, dense_feature))

        url = reverse("admin:mapping_spatialfeature_change", args=(dense_feature.id,))
        response = superuser_client.post(url, data=post_data, format="multipart")

        assert response.status_code == 302, getattr(response, "content", b"")

        dense_feature.refresh_from_db()
        assert dense_feature.name == "Renamed Road Network"
        # Geometry is untouched by a name-only edit.
        assert dense_feature.feature_geometry.equals_exact(original_geometry, tolerance=1e-9)

    def test_change_view_geometry_is_readonly(self, superuser_client, dense_feature):
        """On the change view the geometry field is read-only and shown as a summary."""
        admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
        request = superuser_client.get(
            reverse("admin:mapping_spatialfeature_change", args=(dense_feature.id,))
        ).wsgi_request

        readonly = admin_instance.get_readonly_fields(request, obj=dense_feature)
        assert "feature_geometry_summary" in readonly

        fieldset_fields = admin_instance.get_fieldsets(request, obj=dense_feature)[0][1]["fields"]
        assert "feature_geometry_summary" in fieldset_fields
        assert "feature_geometry" not in fieldset_fields

        with override_settings(MAPPING_ADMIN_GEOMETRY_EDIT_MAX_VERTICES=10_000):
            summary = admin_instance.feature_geometry_summary(dense_feature)
        assert "MultiLineString" in summary
        assert "vertices" in summary
        assert "10,000" in summary
        assert "QGIS" in summary

    def test_geometry_summary_uses_geodjango_casing_over_raw_sql_annotation(self, dense_feature):
        """The RawSQL `geometry_type` annotation is UPPERCASE (PostGIS geometryType());
        the summary must always prefer GeoDjango's mixed-case geom.geom_type instead.
        """
        admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
        dense_feature.geometry_type = "MULTILINESTRING"

        summary = admin_instance.feature_geometry_summary(dense_feature)

        assert "MultiLineString" in summary
        assert "MULTILINESTRING" not in summary

    def test_add_view_geometry_is_editable(self, superuser_client):
        """On the add view the editable geometry widget is retained."""
        admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
        request = superuser_client.get(reverse("admin:mapping_spatialfeature_add")).wsgi_request

        readonly = admin_instance.get_readonly_fields(request, obj=None)
        assert "feature_geometry_summary" not in readonly

        fieldset_fields = admin_instance.get_fieldsets(request, obj=None)[0][1]["fields"]
        assert "feature_geometry" in fieldset_fields
        assert "feature_geometry_summary" not in fieldset_fields

    def test_geometry_summary_handles_missing_geometry(self):
        """feature_geometry_summary degrades gracefully when geometry is None."""
        admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
        feature = SpatialFeature(name="No geom")
        feature.feature_geometry = None
        assert admin_instance.feature_geometry_summary(feature) == "<no geometry>"

    def test_change_view_small_geometry_stays_editable(self, superuser_client, feature_type1):
        """A geometry at or below the vertex threshold keeps the editable widget on the change view."""
        feature = SpatialFeature.objects.create(
            name="Small Feature",
            feature_type=feature_type1,
            feature_geometry=LineString([(0, 0), (1, 1), (2, 2)], srid=4326),
        )
        admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
        request = superuser_client.get(reverse("admin:mapping_spatialfeature_change", args=(feature.id,))).wsgi_request

        readonly = admin_instance.get_readonly_fields(request, obj=feature)
        assert "feature_geometry_summary" not in readonly

        fieldset_fields = admin_instance.get_fieldsets(request, obj=feature)[0][1]["fields"]
        assert "feature_geometry" in fieldset_fields
        assert "feature_geometry_summary" not in fieldset_fields

        form_class = admin_instance.get_form(request, obj=feature)
        assert "feature_geometry" in form_class.base_fields

    def test_change_view_geometry_exactly_at_threshold_stays_editable(self, superuser_client, feature_type1):
        """A geometry with exactly the threshold's vertex count is still editable (boundary case)."""
        feature = SpatialFeature.objects.create(
            name="Boundary Feature",
            feature_type=feature_type1,
            feature_geometry=LineString([(index * 0.001, index * 0.001) for index in range(5)], srid=4326),
        )
        assert feature.feature_geometry.num_coords == 5

        with override_settings(MAPPING_ADMIN_GEOMETRY_EDIT_MAX_VERTICES=5):
            admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
            request = superuser_client.get(
                reverse("admin:mapping_spatialfeature_change", args=(feature.id,))
            ).wsgi_request

            readonly = admin_instance.get_readonly_fields(request, obj=feature)
            assert "feature_geometry_summary" not in readonly

            fieldset_fields = admin_instance.get_fieldsets(request, obj=feature)[0][1]["fields"]
            assert "feature_geometry" in fieldset_fields
            assert "feature_geometry_summary" not in fieldset_fields

    def test_change_view_none_geometry_stays_editable(self, superuser_client, feature_type1):
        """A feature with no geometry keeps the editable widget rather than the summary."""
        # feature_geometry has no database-level default and is NOT NULL, so a
        # persisted row always has a geometry; simulate the "no geometry" case the
        # same way as test_geometry_summary_handles_missing_geometry, by clearing
        # the in-memory attribute on an otherwise-persisted instance.
        feature = SpatialFeature.objects.create(
            name="No Geometry Feature",
            feature_type=feature_type1,
            feature_geometry=LineString([(0, 0), (1, 1)], srid=4326),
        )
        feature.feature_geometry = None
        admin_instance = SpatialFeatureAdmin(SpatialFeature, AdminSite())
        request = superuser_client.get(reverse("admin:mapping_spatialfeature_change", args=(feature.id,))).wsgi_request

        readonly = admin_instance.get_readonly_fields(request, obj=feature)
        assert "feature_geometry_summary" not in readonly

        fieldset_fields = admin_instance.get_fieldsets(request, obj=feature)[0][1]["fields"]
        assert "feature_geometry" in fieldset_fields
        assert "feature_geometry_summary" not in fieldset_fields
