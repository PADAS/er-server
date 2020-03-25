import logging
from unittest.mock import patch

from django.core.files import File

from mapping.models import (FeatureSet, FeatureType, PointFeature,
                            PolygonFeature, SpatialFeature, SpatialFeatureType)
from mapping.spatialfile_utils import process_spatialfile
from mapping.tests.base_test import BaseTest

logger = logging.getLogger(__name__)


class BaseFile(object):
    def __init__(self, id, data, feature_type, layer_number, id_field, name_field):
        self.id = id
        self.data = data
        self.feature_type = feature_type
        self.layer_number = layer_number
        self.id_field = id_field
        self.name_field = name_field


class MockSpatialFile(BaseFile):
    def __init__(self, id, data, feature_type, layer_number, id_field, name_field, feature_set):
        self.feature_set = feature_set
        super().__init__(id, data, feature_type, layer_number, id_field, name_field)

MockSpatialFile.__name__ = 'SpatialFile'


class MockSpatialFeatureFile(BaseFile):
    def __init__(self, id, data, feature_type, layer_number, id_field, name_field, feature_types_file):
        self.feature_types_file = feature_types_file
        super().__init__(id, data, feature_type, layer_number, id_field, name_field)

MockSpatialFeatureFile.__name__ = 'SpatialFeatureFile'


class Filedata(object):
    def __init__(self, name, path, url=None):
        self.name = name
        self.path = path
        self.url = url


class TestSpatialFile(BaseTest):
    def test_geojson_file_upload(self):
        logger.info('GeoJson file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Water Points')
        dummy_feature_set = FeatureSet.objects.create(name='Water')
        dummy_feature_set.types.add(dummy_feature_type)

        data = File(open('./mapping/tests/NRT_Water_Points-2.geojson', 'rb' ))

        spatialfile = MockSpatialFile(1, data, dummy_feature_type, 0, 'globalid', 'Name', dummy_feature_set)

        process_spatialfile(spatialfile)
        point_feature = PointFeature.objects.all()[0]
        self.assertEqual(dummy_feature_type, point_feature.type)
        self.assertEqual(dummy_feature_set, point_feature.featureset)
        logger.info('GeoJson file test complete.')

    def test_shapefile_upload(self):
        logger.info('Shape-file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Settlements')
        dummy_feature_set = FeatureSet.objects.create(name='Boundaries')
        dummy_feature_set.types.add(dummy_feature_type)

        data = File(open('./mapping/tests/testdata/Grbnd_New.zip', 'rb'))
        spatialfile = MockSpatialFile(1, data, dummy_feature_type, 0, 'globalid', 'Name', dummy_feature_set)

        process_spatialfile(spatialfile)
        point_feature = PolygonFeature.objects.all()[0]
        self.assertEqual(dummy_feature_type, point_feature.type)
        self.assertEqual(dummy_feature_set, point_feature.featureset)
        logger.info('Shape-file test complete.')

    def test_loading_a_geojson_file_and_featuretypes(self):
        logger.info('Shape-file name-field test started.')

        data = File(open('./mapping/tests/testdata/wells_closed_points.geojson', 'rb'))
        feature_types_file = File(open('./mapping/tests/testdata/spatial_feature_types.geojson', 'rb'))
        spatialfile = MockSpatialFeatureFile(1, data, None, 0, 'globalid', 'Name', feature_types_file)

        with self.settings(UI_SITE_URL='http://www.majete.com'):
            process_spatialfile(spatialfile)
            self.assertEqual(SpatialFeatureType.objects.count(), 214)
            self.assertEqual(SpatialFeature.objects.count(), 6)

    def test_spatial_feature_file_upload(self):
        logger.info('Shape-file test started.')

        data = File(open('./mapping/tests/testdata/Matlamamba.zip', 'rb'))
        spatialfile = MockSpatialFeatureFile(1, data, None, 0, 'globalid', 'Name', None)
        process_spatialfile(spatialfile)

        self.assertEquals(SpatialFeature.objects.count(), 2)
