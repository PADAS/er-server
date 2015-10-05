import simplejson
from itertools import chain

from django.core.serializers import serialize
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.views.generic import View

from mapping.models import PolygonFeature, LineFeature, PointFeature, BaseMap


class FeatureListJsonView(View):
    """
    A simple list of vector layers available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        response_data = {'das_api_stuff': 'goes_here', 'features': []}
        features = list(chain(PolygonFeature.objects.all(), LineFeature.objects.all(), PointFeature.objects.all()))
        for feature in features:
            response_data['features'].append({
                'name': feature.name,
                'type': feature.type,
                'description': feature.description if feature.description else '',
                'geojson_url': reverse('mapping-feature-geojson', args=[feature.id.hex]),
            })
        return HttpResponse(simplejson.dumps(response_data), content_type='application/json')


class FeatureGeoJsonView(View):
    def get(self, request, feature_id):
        feature = serialize('geojson',
                            list(chain(PolygonFeature.objects.filter(id=feature_id),
                                       LineFeature.objects.filter(id=feature_id),
                                       PointFeature.objects.filter(id=feature_id))),
                            fields='name, type, presentation, description, feature_geometry,'
                            )
        return HttpResponse(feature, content_type='application/json')


class BaseMapListJsonView(View):
    """
    A simple list of raster layers available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        # todo:  should draw its list from the raster tables.
        response_data = {'das_api_stuff': 'goes_here', 'base_maps': []}
        base_maps = BaseMap.objects.all()
        for base_map in base_maps:
            response_data['base_maps'].append({
                'name': base_map.name,
                'description': base_map.description if base_map.description else '',
                'raster_file': base_map.raster_file,
                # todo:  this is nonsense right now ... it should point to the raster tiles url for the tif
                'tms_url': '{0}/{{z}}/{{x}}/{{y}}.png'.format(
                    reverse('mapping-tile-sample', args=[base_map.raster_file])),
            })
        return HttpResponse(simplejson.dumps(response_data), content_type='application/json')
