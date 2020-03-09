import functools
import json
import logging

from unittest.mock import patch

from core.tests import BaseAPITest
from mapping.models import (ArcgisConfiguration, ArcgisGroup, SpatialFeature, ArcgisItem,
                            SpatialFeatureType)
from mapping.esri_integration import (arcgis_authentication, extract_features,
                           import_featuretype_presentation, search_groups,
                           update_db_groups)
from observations.utils import convert_date_string
logger = logging.getLogger(__name__)


def _lazy_property(fn):
    attr_name = '_lazy_' + fn.__name__

    @property
    @functools.wraps(fn)
    def _lazy_property(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, fn(self))
        return getattr(self, attr_name)
    return _lazy_property

class MockGIS(object):
    def __init__(self, url=None, username=None, password=None):
        self.url = url
        self.username = username
        self.password = password

    @_lazy_property
    def groups(self):
        return MockGroup(self)

class MockGroup(object):
    def __init__(self, url):
        self.url =url
    
    @classmethod
    def search(self, query=None, max_groups=None, outside_org=None):
        if query:
            filtered_instances = []
            for i in Group.instances:
                if query in i.title:
                    filtered_instances.append(i)
            return filtered_instances
        else:
            return [g for g in Group.instances if g.owner and g.owner=='test_username']


class Group(object):
    instances = []
    def __init__(self, title, id, owner):
        self.title = title
        self.id = id
        self.owner = owner
        self.__class__.instances.append(self)
    

class TestArcGisIntegration(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.test_config = ArcgisConfiguration.objects.create(
            config_name='test_config',
            username='test_username',
            password='test_pass'
        )
        # Create a GIS account
        self.gis_account = MockGIS(
            None, username=self.test_config.username, password=self.test_config.password)

        self.create_groups()
        self.gis_group = Group.instances[0]

        self.arcgis_item = ArcgisItem.objects.create(
            id=self.gis_group.id,
            name=self.gis_group.title,
            arcgis_config=self.test_config
        )

    def create_groups(self):
        groups = {'lewa':self.test_config.username, 'Africa Parks':None, 'Africa Semi arid areas':None}
        wfs_group_titles = [g.title for g in Group.instances]
        for title, owner in groups.items():
            if title not in wfs_group_titles:
                Group(title=title, id=len(Group.instances)+1, owner=owner)


    def test_unique_value_renderer_line(self):
        json_dict = self._read_test_data('./mapping/tests/testdata/line-renderer.json')
        self._verify_types(json_dict)

        for t in SpatialFeatureType.objects.all():
            keys = t.presentation.keys()
            self.assertTrue('stroke' in keys)
            self.assertTrue('stroke-width' in keys)
            self.assertTrue('stroke-opacity' in keys)

    def test_unique_value_renderer_polygon(self):
        json_dict = self._read_test_data('./mapping/tests/testdata/polygon-renderer.json')
        self._verify_types(json_dict)

        for t in SpatialFeatureType.objects.all():
            keys = t.presentation.keys()
            self.assertTrue('fill' in keys)
            self.assertTrue('fill-opacity' in keys)

    def test_unique_value_renderer_point(self):
        json_dict = self._read_test_data('./mapping/tests/testdata/point-renderer.json')
        self._verify_types(json_dict)

    def test_simple_renderer(self):
        pass

    def _verify_types(self, json_dict):
        renderer = Renderer(json_dict['renderer'])
        types = [info.value for info in renderer.uniqueValueInfos]
        types.sort()
        prez = import_featuretype_presentation(renderer)

        self.assertIsNone(prez)
        self.assertEqual(len(types), SpatialFeatureType.objects.count())
        sfts = [t for t in SpatialFeatureType.objects.all()]
        sfts_names = [t.name for t in sfts]
        sfts_names.sort()
        self.assertEqual(types, sfts_names)

    def _read_test_data(self, filepath):
        renderer = None
        try:
            with open(filepath, 'r') as f:
                renderer = json.load(f)
        except Exception as ex:
            logger.exception(ex)

        return renderer

    @patch('arcgis.gis.GIS', MockGIS)
    def test_authentication(self):
        gis = arcgis_authentication(None, self.test_config)
        self.assertTrue(gis)

    def load_features(self):
        with open('./mapping/tests/testdata/Built_point.geojson', 'rb') as geojson_file:
            extract_features(self.test_config, self.gis_group,
                             self.gis_group.title, geojson_file.read().decode("utf-8"), [], [], self.arcgis_item.id)

    @patch('arcgis.gis.GIS', MockGIS)
    def test_groups_loaded_without_search_text(self):
        groups = search_groups(self.gis_account, self.test_config)

        # Only the users groups are returned, just one in this case
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0].owner==self.test_config.username)


    @patch('arcgis.gis.GIS', MockGIS)
    def test_groups_loaded_when_search_text_is_provided(self):
        self.test_config.search_text ='Africa'
        self.test_config.save()
        groups = search_groups(self.gis_account, self.test_config)

        # Two groups returned which contain africa in the name or content
        self.assertEqual(len(groups), 2)

    def test_extract_features_with_features_park_name_not_set(self):
        groups_before_config = SpatialFeature.objects.all().count()
        self.assertEqual(groups_before_config, 0)
        self.load_features()

        groups_after_config = SpatialFeature.objects.all().count()
        self.assertEqual(groups_after_config, 0)

    def test_extract_features_into_er_from_loaded_file_with_valid_park_content(self):
        with self.settings(UI_SITE_URL='http://www.liwonde.com'):
            groups_before_config = SpatialFeature.objects.all().count()
            self.assertEqual(groups_before_config, 0)
            self.load_features()

            groups_after_config = SpatialFeature.objects.all().count()
            self.assertEqual(groups_after_config, 41)

    def test_new_spatial_feature_types_created_from_new_features(self):
        with self.settings(UI_SITE_URL='http://www.liwonde.com'):
            feature_types_before_config = SpatialFeatureType.objects.all().count()
            self.assertEqual(feature_types_before_config, 0)
            self.load_features()

            feature_types_after_config = SpatialFeatureType.objects.all().count()
            self.assertEqual(feature_types_after_config, 7)

    def test_deleted_feature_from_esri(self):
        self.load_features()

        features_originally = SpatialFeature.objects.all().count()
        self.assertEqual(features_originally, 214)

        with open('./mapping/tests/testdata/Built_point.geojson', 'r') as f:
            data = json.load(f)

            # 2 features deleted from the online groups feature
            data['features'] = data['features'][:-2]
            extract_features(self.test_config, self.gis_group,
                                self.gis_group.title, json.dumps(data), [], [], self.arcgis_item.id)

        after_features_deletion = SpatialFeature.objects.all().count()
        self.assertEqual(after_features_deletion, 219)


    def test_updated_feature_update_from_esri(self):
        self.load_features()

        initial_mponda = SpatialFeature.objects.get(name='Mponda')
        prev_mponda_coordinates = [coord for coord in initial_mponda.feature_geometry]

        self.assertEqual(prev_mponda_coordinates, [35.2432244949146, -14.457755073238])
        with open('./mapping/tests/testdata/Built_point.geojson', 'r') as f:
            data = json.load(f)
            for feature in data['features']:
                if feature["properties"]["Name"] == initial_mponda.name:

                    # Update feature geometry
                    feature["geometry"]["coordinates"] = [34.54, -15.77]
            extract_features(self.test_config, self.gis_group,
                                self.gis_group.title, json.dumps(data), [], [], self.arcgis_item.id)

        updated_mponda = SpatialFeature.objects.get(name='Mponda')
        new_mponda_coordinates = [coord for coord in updated_mponda.feature_geometry]
        
        self.assertEqual(new_mponda_coordinates, [34.54, -15.77])
        self.assertTrue(prev_mponda_coordinates != new_mponda_coordinates)


class Renderer:
    def __init__(self, json_dict):
        self.type = json_dict['type']
        self.uniqueValueInfos = [UniqueValueInfo(info) for info in json_dict['uniqueValueInfos']]


class UniqueValueInfo:
    def __init__(self, json_dict):
        self.value = json_dict['value']
        self.symbol = Symbol(json_dict['symbol'])


class Symbol:
    def __init__(self, json_dict):
        self.type = json_dict['type']
        if json_dict.get('color'):
            self.color = [int(i) for i in json_dict['color']]
        self.width = float(json_dict.get('width')) if json_dict.get('width') else 0.0
        if json_dict.get('imageData'):
            self.imageData = json_dict.get('imageData')
