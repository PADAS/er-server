import logging

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from mapping.models import (FeatureSet, FeatureType, PointFeature,
                            PolygonFeature, SpatialFeature, SpatialFeatureFile,
                            SpatialFile, SpatialFeatureType)
from mapping.tasks import extract_features
from mapping.tests.base_test import BaseTest

logger = logging.getLogger(__name__)


class TestSpatialFile(BaseTest):
    def test_geojson_file_upload(self):
        logger.info('GeoJson file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Water Points')
        dummy_feature_set = FeatureSet.objects.create(name='Water')
        dummy_feature_set.types.add(dummy_feature_type)

        with open('./mapping/tests/NRT_Water_Points-2.geojson',
                  'rb') as geojson_file:
            spatial_file = SpatialFile(
                name='GeoJson test', data=SimpleUploadedFile(
                    'dummy.geojson', geojson_file.read()),
                feature_type=dummy_feature_type, feature_set=dummy_feature_set, 
                name_field='NRT'
            )
            spatial_file.clean()
            spatial_file.save()
        # load files
        extract_features(spatial_file.data.path, 'ste', spatial_file, featureset=dummy_feature_set.name)

        point_feature = PointFeature.objects.all()[0]
        self.assertEqual(dummy_feature_type, point_feature.type)
        self.assertEqual(dummy_feature_set, point_feature.featureset)
        logger.info('GeoJson file test complete.')

    def test_shapefile_upload(self):
        logger.info('Shape-file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Settlements')
        dummy_feature_set = FeatureSet.objects.create(name='Boundaries')
        dummy_feature_set.types.add(dummy_feature_type)

        with open('./mapping/tests/Grbnd_New.zip', 'rb') as shapefile:
            spatial_file = SpatialFile(
                name='Shapefile test', data=SimpleUploadedFile(
                    'Grbnd_New.zip', shapefile.read()),
                feature_type=dummy_feature_type, feature_set=dummy_feature_set,
                name_field='Grb'
            )
            spatial_file.clean()
            spatial_file.save()
        
        # load features
        path = spatial_file.data.path.split('.')[0]+ '/Grbnd_New.SHP'
        extract_features(path, 'ste', spatial_file, featureset=dummy_feature_set.name)

        point_feature = PolygonFeature.objects.all()[0]
        self.assertEqual(dummy_feature_type, point_feature.type)
        self.assertEqual(dummy_feature_set, point_feature.featureset)
        logger.info('Shape-file test complete.')

    def test_loading_a_geojson_file_and_featuretypes(self):
        logger.info('Shape-file name-field test started.')

        with open('./mapping/tests/testdata/Built_point.geojson',
                  'rb') as geojson_file:

            with open('./mapping/tests/NRT_Water_Points-2.geojson',
                      'rb') as feature_types_file:
                spatial_file = SpatialFeatureFile(file_type='geojson',
                    name='GeoJson test', data=SimpleUploadedFile(
                        'dummy.geojson', geojson_file.read()),
                    feature_types_file=SimpleUploadedFile(
                        'dummy_types.geojson', feature_types_file.read()))
                spatial_file.clean()
                spatial_file.save()
                logger.info('Shape-file name-field  test complete.')
        # load features
        extract_features(spatial_file.data.path, 'ste', spatial_file)

        # featuretypes added
        self.assertTrue(SpatialFeatureType.objects.count() > 5)
        self.assertEqual(SpatialFeature.objects.count(), 41)

    def test_spatial_feature_file_upload(self):
        logger.info('Shape-file test started.')
        with open('./mapping/tests/Matlamamba.zip', 'rb') as shapefile:
            spatial_file = SpatialFeatureFile(
                name='Shapefile test', data=SimpleUploadedFile(
                    'Matlamamba.zip', shapefile.read()), name_field='Matlamamba')
            spatial_file.clean()
            spatial_file.save()
        
        # Load features
        path = spatial_file.data.path.split('.')[0]+ '/MatlaMamba_Airstrip.shp'
        extract_features(path, 'ste', spatial_file)
        logger.info('Shape-file test complete.')

        self.assertEquals(SpatialFeature.objects.count(), 2)
