from django.test import TestCase

from tracking.models.plugin_base import SourcePlugin
from mapping.models import FeatureType, PolygonFeature
from observations.models import Source
from tracking.models import SavannahPlugin
import tracking

from django.contrib.gis.geos import Polygon, MultiPolygon

import uuid

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

