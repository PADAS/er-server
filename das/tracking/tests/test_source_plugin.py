import uuid
from datetime import datetime, timedelta, timezone

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase

from mapping.models import FeatureType, PolygonFeature
from observations.models import Observation, Source
from tracking.models import SavannahPlugin, SkygisticsSatellitePlugin, skygistics
from tracking.models.plugin_base import DasDefaultTarget, Obs, SourcePlugin


class TestSourcePlugin(TestCase):

    def setUp(self):
        self.source = Source(
            manufacturer_id="some-bogus-id",
            source_type="tracking-device",
            additional=dict(note="created by unit test"),
            id=uuid.uuid4(),
        )
        polygon = Polygon(((0.0, 0.0), (0.0, 50.0), (50.0, 50.0), (50.0, 0.0), (0.0, 0.0)))
        my_polygon = MultiPolygon(polygon)
        feature_type = FeatureType.objects.create(name="my_polygon")
        polygon_feature = PolygonFeature.objects.create(presentation={}, feature_geometry=my_polygon, type=feature_type)
        self.source.save()
        self.plugin = SavannahPlugin.objects.create()
        self.source_plugin = SourcePlugin(source=self.source, plugin=self.plugin)
        self.source_plugin.save()

    def test_source_plugin(self):
        actual = self.source_plugin.plugin
        expected = self.plugin
        self.assertEqual(actual, expected)

    def test_fk_references(self):
        """
        test getting plugin from source_plugin
        """
        actual = self.source.source_plugins.first().plugin
        expected = self.plugin
        self.assertEqual(actual, expected)

    def test_plugin2source(self):
        """
        test getting to source from a concrete plugin.
        """
        plugin = SavannahPlugin.objects.first()
        source_plugin = SourcePlugin.objects.get(plugin_id=plugin.id)
        self.assertEqual(source_plugin.id, self.source_plugin.id)
        self.assertEqual(self.source.id, source_plugin.source.id)

    def test_genericrelation_between_plugin_and_source_plugin(self):

        plugin, created = SavannahPlugin.objects.get_or_create(
            name="dummy-savannah-plugin",
            defaults=dict(service_username="foo", service_password="pwd", service_api_host="0.0.0.0"),
        )

        self.assertTrue(created)
        src, created = Source.objects.get_or_create(
            manufacturer_id="dummy-source-id", defaults=dict(model_name="Dummy", additional={})
        )

        expected, created = SourcePlugin.objects.get_or_create(source=src, defaults=dict(plugin=plugin))

        # This tests the GenericRelation that's in TrackingPlugin.
        source_plugins = plugin.source_plugins.all()
        self.assertTrue(len(source_plugins) == 1)

        self.assertEqual(source_plugins[0].id, expected.id)

    def test_should_run(self):
        plugin = SavannahPlugin.objects.create(name="dummy-savannah-plugin")
        source = Source.objects.create(
            manufacturer_id="asdfas",
            additional={},
        )

        # The latest timestamp is very recent, so we should not run.
        latest_timestamp = datetime.now(tz=timezone.utc)
        sp = SourcePlugin.objects.create(
            source=source, plugin=plugin, cursor_data={"latest_timestamp": latest_timestamp.isoformat()}
        )
        self.assertTrue(not sp.should_run())

        # The latest timestamp is within the quiet period, should we should not run.
        latest_timestamp_late = latest_timestamp - plugin.DEFAULT_REPORT_INTERVAL + timedelta(minutes=2)
        sp = SourcePlugin.objects.create(
            source=source, plugin=plugin, cursor_data={"latest_timestamp": latest_timestamp_late.isoformat()}
        )
        self.assertTrue(not sp.should_run())

        # We've reach a point where the plugin should run.
        latest_timestamp_early = latest_timestamp - plugin.DEFAULT_REPORT_INTERVAL
        sp = SourcePlugin.objects.create(
            source=source, plugin=plugin, cursor_data={"latest_timestamp": latest_timestamp_early.isoformat()}
        )
        self.assertTrue(sp.should_run())

    def test_invalid_skygistic_observations_saved_but_flagged(self):
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        obs_data = skygistics.Observation(
            imei="test_imei",
            latitude=90,
            longitude=180,
            voltage="12.9",
            location="test_location",
            temperature="103",
            recorded_at=datetime.now(tz=timezone.utc),
            received_time=datetime.now(tz=timezone.utc),
        )

        observation = plugin._transform(self.source, obs_data)
        validated_obs = source_plugin.validate_obs_location(observation)

        with DasDefaultTarget() as t:
            t.send(validated_obs)

        result = Observation.objects.get(recorded_at=observation.recorded_at)
        self.assertTrue(result.exclusion_flags._value == 2)  # automatically excluded

    def test_validate_obs_location_valid_coordinates(self):
        """Test that valid coordinates are not flagged for exclusion."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with valid coordinates
        observation = Obs(
            source=self.source,
            latitude=45.0,
            longitude=-120.0,
            recorded_at=datetime.now(tz=timezone.utc),
            additional={},
            exclusion_flags=0,
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should not be flagged for exclusion
        self.assertEqual(validated_obs.exclusion_flags, 0)
        self.assertEqual(validated_obs.latitude, 45.0)
        self.assertEqual(validated_obs.longitude, -120.0)

    def test_validate_obs_location_180_90_coordinates(self):
        """Test that coordinates (180, 90) are flagged for exclusion."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with invalid coordinates (180, 90)
        observation = Obs(
            source=self.source,
            latitude=90.0,
            longitude=180.0,
            recorded_at=datetime.now(tz=timezone.utc),
            additional={},
            exclusion_flags=0,
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should be flagged for automatic exclusion
        self.assertEqual(validated_obs.exclusion_flags, Observation.EXCLUDED_AUTOMATICALLY)
        self.assertEqual(validated_obs.latitude, 90.0)
        self.assertEqual(validated_obs.longitude, 180.0)

    def test_validate_obs_location_0_0_coordinates(self):
        """Test that coordinates (0, 0) are flagged for exclusion."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with invalid coordinates (0, 0)
        observation = Obs(
            source=self.source,
            latitude=0.0,
            longitude=0.0,
            recorded_at=datetime.now(tz=timezone.utc),
            additional={},
            exclusion_flags=0,
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should be flagged for automatic exclusion
        self.assertEqual(validated_obs.exclusion_flags, Observation.EXCLUDED_AUTOMATICALLY)
        self.assertEqual(validated_obs.latitude, 0.0)
        self.assertEqual(validated_obs.longitude, 0.0)

    def test_validate_obs_location_future_timestamp(self):
        """Test that observations with future timestamps are flagged for exclusion."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with future timestamp (beyond 7 days from now)
        future_time = datetime.now(tz=timezone.utc) + timedelta(days=10)
        observation = Obs(
            source=self.source,
            latitude=45.0,
            longitude=-120.0,
            recorded_at=future_time,
            additional={},
            exclusion_flags=0,
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should be flagged for automatic exclusion
        self.assertEqual(validated_obs.exclusion_flags, Observation.EXCLUDED_AUTOMATICALLY)
        self.assertEqual(validated_obs.recorded_at, future_time)

    def test_validate_obs_location_past_timestamp_within_limit(self):
        """Test that observations with past timestamps within the limit are not flagged."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with past timestamp (within 7 days)
        past_time = datetime.now(tz=timezone.utc) - timedelta(days=3)
        observation = Obs(
            source=self.source, latitude=45.0, longitude=-120.0, recorded_at=past_time, additional={}, exclusion_flags=0
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should not be flagged for exclusion
        self.assertEqual(validated_obs.exclusion_flags, 0)
        self.assertEqual(validated_obs.recorded_at, past_time)

    def test_validate_obs_location_future_timestamp_within_limit(self):
        """Test that observations with future timestamps within the limit are not flagged."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with future timestamp (within 7 days)
        future_time = datetime.now(tz=timezone.utc) + timedelta(days=3)
        observation = Obs(
            source=self.source,
            latitude=45.0,
            longitude=-120.0,
            recorded_at=future_time,
            additional={},
            exclusion_flags=0,
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should not be flagged for exclusion
        self.assertEqual(validated_obs.exclusion_flags, 0)
        self.assertEqual(validated_obs.recorded_at, future_time)

    def test_validate_obs_location_coordinates_with_decimal_precision(self):
        """Test that coordinates are compared as integers for validation."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with coordinates that round to (180, 90)
        observation = Obs(
            source=self.source,
            latitude=90.9,  # int(90.9) = 90
            longitude=180.1,  # int(180.1) = 180
            recorded_at=datetime.now(tz=timezone.utc),
            additional={},
            exclusion_flags=0,
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should be flagged for automatic exclusion since int(90.9) = 90 and int(180.1) = 180
        self.assertEqual(validated_obs.exclusion_flags, Observation.EXCLUDED_AUTOMATICALLY)

    def test_validate_obs_location_preserves_existing_exclusion_flags(self):
        """Test that the method preserves existing exclusion flags when not adding new ones."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with existing exclusion flags
        observation = Obs(
            source=self.source,
            latitude=45.0,
            longitude=-120.0,
            recorded_at=datetime.now(tz=timezone.utc),
            additional={},
            exclusion_flags=Observation.EXCLUDED_MANUALLY,  # Existing flag
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should preserve existing flags when coordinates are valid
        self.assertEqual(validated_obs.exclusion_flags, Observation.EXCLUDED_MANUALLY)

    def test_validate_obs_location_multiple_conditions(self):
        """Test that multiple invalid conditions result in exclusion flag."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Create observation with both invalid coordinates and future timestamp
        future_time = datetime.now(timezone.utc) + timedelta(days=10)
        observation = Obs(
            source=self.source,
            latitude=90.0,
            longitude=180.0,
            recorded_at=future_time,
            additional={},
            exclusion_flags=0,
        )

        validated_obs = source_plugin.validate_obs_location(observation)

        # Should be flagged for automatic exclusion
        self.assertEqual(validated_obs.exclusion_flags, Observation.EXCLUDED_AUTOMATICALLY)

    def test_validate_obs_location_edge_case_coordinates(self):
        """Test edge cases around the invalid coordinate boundaries."""
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        # Test coordinates just outside the invalid ranges
        test_cases = [
            (89.9, 179.9, False),  # Just outside (90, 180) - should not be flagged
            (90.0, 180.0, True),  # Exactly (90, 180) - should be flagged
            (0.0, 0.0, True),  # Exactly (0, 0) - should be flagged
        ]

        for lat, lon, should_be_flagged in test_cases:
            observation = Obs(
                source=self.source,
                latitude=lat,
                longitude=lon,
                recorded_at=datetime.now(tz=timezone.utc),
                additional={},
                exclusion_flags=0,
            )

            validated_obs = source_plugin.validate_obs_location(observation)

            if should_be_flagged:
                self.assertEqual(
                    validated_obs.exclusion_flags,
                    Observation.EXCLUDED_AUTOMATICALLY,
                    f"Coordinates ({lat}, {lon}) should be flagged",
                )
            else:
                self.assertEqual(validated_obs.exclusion_flags, 0, f"Coordinates ({lat}, {lon}) should not be flagged")
