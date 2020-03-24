import logging
from unittest.mock import patch

from mapping.models import (FeatureSet, FeatureType, PointFeature,
                            PolygonFeature, SpatialFeature, SpatialFeatureType)
from mapping.spatialfile_utils import extract_features_from_files
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

        filepath = './mapping/tests/NRT_Water_Points-2.geojson'
        data = Filedata(name=filepath, url=filepath, path=filepath)

        spatialfile = MockSpatialFile(1, data, dummy_feature_type, 0, 'globalid', 'Name', dummy_feature_set)

        with patch('mapping.spatialfile_utils.onlinestorage', False):
            extract_features_from_files(spatialfile, 'SpatialFile')
            point_feature = PointFeature.objects.all()[0]
            self.assertEqual(dummy_feature_type, point_feature.type)
            self.assertEqual(dummy_feature_set, point_feature.featureset)
            logger.info('GeoJson file test complete.')

    def test_shapefile_upload(self):
        logger.info('Shape-file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Settlements')
        dummy_feature_set = FeatureSet.objects.create(name='Boundaries')
        dummy_feature_set.types.add(dummy_feature_type)

        filepath = './mapping/tests/testdata/Grbnd_New/Grbnd_New.SHP'
        data = Filedata(name=filepath, url=filepath, path=filepath)
        spatialfile = MockSpatialFile(1, data, dummy_feature_type, 0, 'globalid', 'Name', dummy_feature_set)

        with patch('mapping.spatialfile_utils.onlinestorage', False):
            extract_features_from_files(spatialfile, 'SpatialFile')

            point_feature = PolygonFeature.objects.all()[0]
            self.assertEqual(dummy_feature_type, point_feature.type)
            self.assertEqual(dummy_feature_set, point_feature.featureset)
            logger.info('Shape-file test complete.')

    def test_loading_a_geojson_file_and_featuretypes(self):
        logger.info('Shape-file name-field test started.')

        filepath = './mapping/tests/testdata/wells_closed_points.geojson'
        types_file = './mapping/tests/testdata/spatial_feature_types.geojson'

        data = Filedata(name=filepath, url=filepath, path=filepath)
        feature_types_file = Filedata(name=types_file, url=types_file, path=types_file)
        spatialfile = MockSpatialFeatureFile(1, data, None, 0, 'globalid', 'Name', feature_types_file)

        with self.settings(UI_SITE_URL='http://www.majete.com'):
            with patch('mapping.spatialfile_utils.onlinestorage', False):
                extract_features_from_files(spatialfile, 'SpatialFeatureFile')

                self.assertEqual(SpatialFeatureType.objects.count(), 214)
                self.assertEqual(SpatialFeature.objects.count(), 6)

    def test_spatial_feature_file_upload(self):
        logger.info('Shape-file test started.')

        filepath = './mapping/tests/testdata/Matlamamba/MatlaMamba_Airstrip.shp'
        data = Filedata(name=filepath, url=filepath, path=filepath)
        spatialfile = MockSpatialFeatureFile(1, data, None, 0, 'globalid', 'Name', None)
        with patch('mapping.spatialfile_utils.onlinestorage', False):
            extract_features_from_files(spatialfile, 'SpatialFeatureFile')

        self.assertEquals(SpatialFeature.objects.count(), 2)
