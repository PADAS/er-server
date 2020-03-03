import logging
from unittest.mock import patch

from mapping.models import (FeatureSet, FeatureType, PointFeature,
                            PolygonFeature, SpatialFeature, SpatialFeatureType)
from mapping.tasks import extract_features_from_files
from mapping.tests.base_test import BaseTest

logger = logging.getLogger(__name__)


class TestSpatialFile(BaseTest):
    def test_geojson_file_upload(self):
        logger.info('GeoJson file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Water Points')
        dummy_feature_set = FeatureSet.objects.create(name='Water')
        dummy_feature_set.types.add(dummy_feature_type)

        with patch('mapping.utils.cleanup_files') as mock_cleanup:
            mock_cleanup.return_value = None
            extract_features_from_files('./mapping/tests/NRT_Water_Points-2.geojson', 'ste', None,
                                        featuretype=dummy_feature_type.name,
                                        featureset=dummy_feature_set.name, name_field='')

            point_feature = PointFeature.objects.all()[0]
            self.assertEqual(dummy_feature_type, point_feature.type)
            self.assertEqual(dummy_feature_set, point_feature.featureset)
            logger.info('GeoJson file test complete.')

    def test_shapefile_upload(self):
        logger.info('Shape-file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Settlements')
        dummy_feature_set = FeatureSet.objects.create(name='Boundaries')
        dummy_feature_set.types.add(dummy_feature_type)

        path = './mapping/tests/testdata/Grbnd_New/Grbnd_New.SHP'
        with patch('mapping.utils.cleanup_files') as mock_cleanup:
            mock_cleanup.return_value = None
            extract_features_from_files(path, 'ste', None, featuretype=dummy_feature_type.name,
                                        featureset=dummy_feature_set.name, name_field='')

            point_feature = PolygonFeature.objects.all()[0]
            self.assertEqual(dummy_feature_type, point_feature.type)
            self.assertEqual(dummy_feature_set, point_feature.featureset)
            logger.info('Shape-file test complete.')

    def test_loading_a_geojson_file_and_featuretypes(self):
        logger.info('Shape-file name-field test started.')

        # load features
        with self.settings(UI_SITE_URL='http://www.majete.com'):
            with patch('mapping.utils.cleanup_files') as mock_cleanup:
                mock_cleanup.return_value = None
                data_file_path = ['./mapping/tests/testdata/wells_closed_points.geojson']
                feature_types_file = './mapping/tests/testdata/spatial_feature_types.geojson'
                extract_features_from_files(data_file_path, 'ste', None, feature_types_file, name_field='', )

                # featuretypes added
                self.assertEqual(SpatialFeatureType.objects.count(), 37)
                self.assertEqual(SpatialFeature.objects.count(), 6)

    def test_spatial_feature_file_upload(self):
        logger.info('Shape-file test started.')

        # Load features
        path = './mapping/tests/testdata/Matlamamba/MatlaMamba_Airstrip.shp'
        with patch('mapping.utils.cleanup_files') as mock_cleanup:
            mock_cleanup.return_value = None
            extract_features_from_files(path, 'ste', None, name_field='')
        logger.info('Shape-file test complete.')

        self.assertEquals(SpatialFeature.objects.count(), 2)
