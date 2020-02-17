import json
import logging

from core.tests import BaseAPITest
from mapping.utils import import_featuretype_presentation
from mapping.models import SpatialFeatureType

logger = logging.getLogger(__name__)


class TestArcGisIntegration(BaseAPITest):

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


