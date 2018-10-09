import logging

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from mapping.models import SpatialFile, FeatureSet, FeatureType, PointFeature, \
    PolygonFeature


logger = logging.getLogger(__name__)


class TestSpatialFile(TestCase):
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
                feature_type=dummy_feature_type, feature_set=dummy_feature_set
            )
            spatial_file.clean()
            spatial_file.save()

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
                name_field='AREANAME'
            )
            spatial_file.clean()
            spatial_file.save()

        point_feature = PolygonFeature.objects.all()[0]
        self.assertEqual(dummy_feature_type, point_feature.type)
        self.assertEqual(dummy_feature_set, point_feature.featureset)
        logger.info('Shape-file test complete.')

    def test_shapefile_name_field_mismatch(self):
        logger.info('Shape-file name-field test started.')
        dummy_feature_type = FeatureType.objects.create(name='Cartography')
        dummy_feature_set = FeatureSet.objects.create(name='Boundaries')
        dummy_feature_set.types.add(dummy_feature_type)

        with open('./mapping/tests/Grbnd_New.zip', 'rb') as shapefile:
            spatial_file = SpatialFile(
                name='Shapefile test', data=SimpleUploadedFile(
                    'Grbnd_New.zip', shapefile.read()),
                feature_type=dummy_feature_type, feature_set=dummy_feature_set
            )
            with self.assertRaises(ValidationError):
                spatial_file.clean()
                spatial_file.save()
        logger.info('Shape-file name-field  test complete.')
