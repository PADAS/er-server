from io import StringIO

import pytest

from django.contrib.gis.geos import Point
from django.core.management import call_command

from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType


@pytest.mark.django_db
class TestPopulateWebmercatorGeometries:
    """Test the populate_webmercator_geometries management command"""

    def test_command_populates_null_webmercator_fields(self, das_tenant):
        """Test that command populates features with null webmercator geometries"""
        dc = DisplayCategory.objects.create(name="CommandTest")
        ft = SpatialFeatureType.objects.create(name="CommandTestType", display_category=dc)

        # Create features and then manually clear webmercator field using update
        feature1 = SpatialFeature.objects.create(feature_type=ft, name="Test1", feature_geometry=Point(1, 1))
        feature2 = SpatialFeature.objects.create(feature_type=ft, name="Test2", feature_geometry=Point(2, 2))

        # Manually set webmercator to null using update to bypass save()
        SpatialFeature.objects.filter(id__in=[feature1.id, feature2.id]).update(feature_geometry_webmercator=None)

        # Verify they're null after update
        feature1.refresh_from_db()
        feature2.refresh_from_db()
        assert feature1.feature_geometry_webmercator is None
        assert feature2.feature_geometry_webmercator is None

        # Run the command with tenant domain
        out = StringIO()
        call_command("populate_webmercator_geometries", tenant_domain=das_tenant.domain, stdout=out)

        # Verify they're populated after command
        feature1.refresh_from_db()
        feature2.refresh_from_db()
        assert feature1.feature_geometry_webmercator is not None
        assert feature1.feature_geometry_webmercator.srid == 3857
        assert feature2.feature_geometry_webmercator is not None
        assert feature2.feature_geometry_webmercator.srid == 3857

        # Check command output
        output = out.getvalue()
        assert "Found 2 SpatialFeatures to process" in output
        assert "Processed: 2" in output

    def test_command_skips_already_populated_features(self, das_tenant):
        """Test that command skips features that already have webmercator geometries"""
        dc = DisplayCategory.objects.create(name="SkipTest")
        ft = SpatialFeatureType.objects.create(name="SkipTestType", display_category=dc)

        # Create feature and let save() populate webmercator
        feature = SpatialFeature.objects.create(feature_type=ft, name="AlreadyPopulated", feature_geometry=Point(3, 3))

        # Should have webmercator geometry from save()
        assert feature.feature_geometry_webmercator is not None
        original_webmercator = feature.feature_geometry_webmercator

        # Run command with tenant domain
        out = StringIO()
        call_command("populate_webmercator_geometries", tenant_domain=das_tenant.domain, stdout=out)

        # Should not have changed
        feature.refresh_from_db()
        assert feature.feature_geometry_webmercator.equals(original_webmercator)

        # Check output indicates no processing needed
        output = out.getvalue()
        assert "No SpatialFeatures need Web Mercator geometry processing" in output

    def test_command_batch_size_parameter(self, das_tenant):
        """Test that command respects batch_size parameter"""
        dc = DisplayCategory.objects.create(name="BatchTest")
        ft = SpatialFeatureType.objects.create(name="BatchTestType", display_category=dc)

        # Create multiple features and then clear webmercator
        features = []
        for i in range(5):
            feature = SpatialFeature.objects.create(feature_type=ft, name=f"BatchTest{i}", feature_geometry=Point(i, i))
            features.append(feature)

        # Clear webmercator fields using update
        feature_ids = [f.id for f in features]
        SpatialFeature.objects.filter(id__in=feature_ids).update(feature_geometry_webmercator=None)

        # Run command with small batch size and tenant domain
        out = StringIO()
        call_command(
            "populate_webmercator_geometries", "--batch-size", "2", tenant_domain=das_tenant.domain, stdout=out
        )

        # All features should be populated
        for feature in features:
            feature.refresh_from_db()
            assert feature.feature_geometry_webmercator is not None
            assert feature.feature_geometry_webmercator.srid == 3857

        # Should show multiple batches processed
        output = out.getvalue()
        assert output.count("Batch") >= 2  # At least 2 batches for 5 items with batch_size=2
        assert "Processed: 5" in output

    def test_command_dry_run_parameter(self, das_tenant):
        """Test that dry run mode doesn't actually update features"""
        dc = DisplayCategory.objects.create(name="DryRunTest")
        ft = SpatialFeatureType.objects.create(name="DryRunTestType", display_category=dc)

        # Create feature and clear webmercator
        feature = SpatialFeature.objects.create(feature_type=ft, name="DryRunTest", feature_geometry=Point(5, 5))
        SpatialFeature.objects.filter(id=feature.id).update(feature_geometry_webmercator=None)

        # Verify it's null
        feature.refresh_from_db()
        assert feature.feature_geometry_webmercator is None

        # Run command in dry run mode with tenant domain
        out = StringIO()
        call_command("populate_webmercator_geometries", "--dry-run", tenant_domain=das_tenant.domain, stdout=out)

        # Should still be null after dry run
        feature.refresh_from_db()
        assert feature.feature_geometry_webmercator is None

        # Check output indicates dry run
        output = out.getvalue()
        assert "DRY RUN" in output
