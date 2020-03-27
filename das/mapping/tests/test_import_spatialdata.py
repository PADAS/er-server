import logging
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.files import File
from django.test import RequestFactory, override_settings, TransactionTestCase
from django.urls import reverse
import django
from accounts.models import User
from core.tests import BaseAPITest
from mapping.admin import SpatialFeatureFileAdmin
from mapping.models import (FeatureSet, FeatureType, PointFeature,
                            PolygonFeature, SpatialFeature, SpatialFeatureFile,
                            SpatialFeatureType, SpatialFile)
from mapping.spatialfile_utils import process_spatialfile
from mapping.tasks import load_spatial_features
logger = logging.getLogger(__name__)


class TestSpatialFile(BaseAPITest):

    def setUp(self):
        super().setUp()
        # self.superuser = User.objects.get(username='admin')
        self.site = AdminSite()
        self.request = RequestFactory()
        self.admin = SpatialFeatureFileAdmin(model=SpatialFeatureFile, admin_site=self.site)
        self.request = self.request.get('/admin')

    def test_geojson_file_upload(self):
        logger.info('GeoJson file test started.')
        dummy_feature_type = FeatureType.objects.create(name='Water Points')
        dummy_feature_set = FeatureSet.objects.create(name='Water')
        dummy_feature_set.types.add(dummy_feature_type)

        data = File(open('./mapping/tests/NRT_Water_Points-2.geojson', 'rb' ))
        spatialfile = SpatialFile.objects.create(data=data, feature_set=dummy_feature_set, feature_type=dummy_feature_type)

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
        spatialfile = SpatialFile.objects.create(data=data, feature_set=dummy_feature_set, feature_type=dummy_feature_type)

        process_spatialfile(spatialfile)
        point_feature = PolygonFeature.objects.all()[0]
        self.assertEqual(dummy_feature_type, point_feature.type)
        self.assertEqual(dummy_feature_set, point_feature.featureset)
        logger.info('Shape-file test complete.')

    def test_loading_a_geojson_file_and_featuretypes(self):
        logger.info('Spatialfile and featuretypes file upload test started.')

        data = File(open('./mapping/tests/testdata/wells_closed_points.geojson', 'rb'))
        feature_types_file = File(open('./mapping/tests/testdata/spatial_feature_types.geojson', 'rb'))
        spatialfile = SpatialFeatureFile.objects.create(data=data, feature_types_file=feature_types_file)

        with self.settings(UI_SITE_URL='http://www.majete.com'):
            process_spatialfile(spatialfile)
            self.assertEqual(SpatialFeatureType.objects.count(), 213)
            self.assertEqual(SpatialFeature.objects.count(), 6)

    def test_spatial_feature_file_upload(self):
        data = File(open('./mapping/tests/testdata/Matlamamba.zip', 'rb'))
        spatialfile = SpatialFeatureFile.objects.create(data=data)
        process_spatialfile(spatialfile)

        self.assertEquals(SpatialFeature.objects.count(), 2)

    def test_updating_spatialfile(self):
        data = File(open('./mapping/tests/testdata/Matlamamba.zip', 'rb' ))
        
        spatialfile = SpatialFeatureFile.objects.create(data=data)

        ModelForm = self.admin.get_form(self.request, spatialfile, change=True)
        form = ModelForm(self.request.POST, self.request.FILES, instance=spatialfile)

        with patch.object(django.db.transaction, 'on_commit', lambda load_spatial_features_from_files: load_spatial_features(spatialfile)):
            self.admin.save_model(self.request, spatialfile, form, True)
            self.assertEquals(SpatialFeature.objects.count(), 2)

            # Update only name and description, no features are affected
            spatialfile.name = 'Matlamamba Lines'
            spatialfile.save
            self.admin.save_model(self.request, spatialfile, form, True)
            self.assertEquals(SpatialFeature.objects.count(), 2)

            # Updated spatialfile on all related features
            self.assertEquals(SpatialFeature.objects.filter(spatialfile=spatialfile).count(), 2)
            
            
            # update data file, new features loaded
            data2 = File(open('./mapping/tests/testdata/wells_closed_points.geojson', 'rb'))
            spatialfile.data = data2
            spatialfile.save()
            self.admin.save_model(self.request, spatialfile, form, True)
            self.assertEquals(SpatialFeature.objects.count(), 6)

            

            



        
        # dummy_feature_type = SpatialFeatureType.objects.create(name='Water Points')

        

        
        # spatialfile.data = data2
        
        
        # # process_spatialfile(spatialfile)
        # self.assertEquals(SpatialFeature.objects.count(), 92)
