from datetime import datetime, timedelta
import pytz

from django.test import TestCase

from tracking.models.plugin_base import SourcePlugin
from mapping.models import FeatureType, PolygonFeature
from observations.models import Source, Observation
from tracking.models import SavannahPlugin, SkygisticsSatellitePlugin, AwtPlugin

from django.contrib.gis.geos import Polygon, MultiPolygon

import uuid
from tracking.models.plugin_base import DasDefaultTarget
from tracking.models import skygistics
class TestSourcePlugin(TestCase):

    def setUp(self):
        self.source = Source(manufacturer_id='some-bogus-id', source_type='tracking-device',
                             additional=dict(note='created by unit test'), id=uuid.uuid4())
        polygon = Polygon(((0.0, 0.0), (0.0, 50.0), (50.0, 50.0), (50.0, 0.0), (0.0, 0.0)))
        my_polygon = MultiPolygon(polygon)
        feature_type = FeatureType.objects.create(name='my_polygon')
        polygon_feature = PolygonFeature.objects.create(
            presentation={},
            feature_geometry=my_polygon,
            type=feature_type
        )
        self.source.save()
        self.plugin = SavannahPlugin.objects.create()
        self.source_plugin = SourcePlugin(source=self.source, plugin=self.plugin)
        self.source_plugin.save()


    def test_source_plugin(self):
        actual = self.source_plugin.plugin
        expected = self.plugin
        self.assertEqual(actual, expected)

    def test_fk_references(self):
        '''
        test getting plugin from source_plugin
        '''
        actual = self.source.source_plugins.first().plugin
        expected = self.plugin
        self.assertEqual(actual, expected)

    def test_plugin2source(self):
        '''
        test getting to source from a concrete plugin.
        '''
        plugin = SavannahPlugin.objects.first()
        source_plugin = SourcePlugin.objects.get(plugin_id=plugin.id)
        self.assertEqual(source_plugin.id, self.source_plugin.id)
        self.assertEqual(self.source.id, source_plugin.source.id)

    def test_genericrelation_between_plugin_and_source_plugin(self):

        plugin, created = SavannahPlugin.objects.get_or_create(name='dummy-savannah-plugin',
                                                      defaults=dict(service_username='foo',
                                                                    service_password='pwd',
                                                                    service_api_host='0.0.0.0'))

        self.assertTrue(created)
        src, created = Source.objects.get_or_create(manufacturer_id='dummy-source-id',
                                           defaults=dict(model_name='Dummy', additional={}))

        expected, created = SourcePlugin.objects.get_or_create(source=src,
                                           defaults=dict(plugin=plugin))

        # This tests the GenericRelation that's in TrackingPlugin.
        source_plugins = plugin.source_plugins.all()
        self.assertTrue(len(source_plugins) == 1)

        self.assertEqual(source_plugins[0].id, expected.id)

    def test_should_run(self):
        plugin = SavannahPlugin.objects.create(name='dummy-savannah-plugin')
        source = Source.objects.create(manufacturer_id='asdfas', additional={}, )

        # The latest timestamp is very recent, so we should not run.
        latest_timestamp = pytz.utc.localize(datetime.utcnow())
        sp = SourcePlugin.objects.create(source=source, plugin=plugin, cursor_data={'latest_timestamp':latest_timestamp.isoformat()})
        self.assertTrue(not sp.should_run())

        # The latest timestamp is within the quiet period, should we should not run.
        latest_timestamp_late = latest_timestamp - plugin.DEFAULT_REPORT_INTERVAL + timedelta(minutes=2)
        sp = SourcePlugin.objects.create(source=source, plugin=plugin, cursor_data={'latest_timestamp':latest_timestamp_late.isoformat()})
        self.assertTrue(not sp.should_run())

        # We've reach a point where the plugin should run.
        latest_timestamp_early = latest_timestamp - plugin.DEFAULT_REPORT_INTERVAL
        sp = SourcePlugin.objects.create(source=source, plugin=plugin, cursor_data={'latest_timestamp':latest_timestamp_early.isoformat()})
        self.assertTrue(sp.should_run())

    def test_invalid_skygistic_observations_saved_but_flagged(self):
        plugin = SkygisticsSatellitePlugin.objects.create()
        source_plugin = SourcePlugin(source=self.source, plugin=plugin)

        obs_data = skygistics.Observation(
            imei='test_imei',
            latitude=90,
            longitude=180,
            voltage="12.9",
            location="test_location",
            temperature="103",
            recorded_at=datetime.now(),
            received_time=datetime.now()
        )

        observation = plugin._transform(self.source, obs_data)
        validated_obs = source_plugin.validate_obs_location(observation)

        with DasDefaultTarget() as t:
            t.send(validated_obs)

        result = Observation.objects.get(recorded_at=observation.recorded_at)
        self.assertTrue(result.exclusion_flags._value == 2) # automatically excluded
