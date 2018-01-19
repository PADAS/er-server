from django.conf.urls import url
from mapping.views import *
from mapping.sample_views import *
from mapping.app_settings import MBTILES_ID_PATTERN

app_name = 'mapping'

urlpatterns = (
    # a list of available features
    url(r'^features/?$', FeatureListJsonView.as_view()),
    # todo:  add caching
    url(r'^feature/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        FeatureGeoJsonView.as_view(), name='mapping-feature-geojson'),

    # a list of available featuresets
    url(r'^featureset/?$', FeatureSetListJsonView.as_view()),
    # the geojson for a particular feature
    url(r'^featureset/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        FeatureSetGeoJsonView.as_view(), name='mapping-featureset-geojson'),

    # a list of available base maps
    url(r'^maps/?$', MapListJsonView.as_view()),

    url(r'^mbtiles/(?P<name>%s)/(?P<z>(\d+|\{z\}))/(?P<x>(\d+|\{x\}))/(?P<y>(\d+|\{y\})).png$' % MBTILES_ID_PATTERN, tile, name="tile"),
    url(r'^mbtiles/(?P<name>%s)/(?P<z>(\d+|\{z\}))/(?P<x>(\d+|\{x\}))/(?P<y>(\d+|\{y\})).grid.json$' % MBTILES_ID_PATTERN, grid, name="grid"),
    url(r'^mbtiles/(?P<name>%s)/preview.png$' % MBTILES_ID_PATTERN, preview, name="preview"),
    url(r'^mbtiles/(?P<name>%s).json$' % MBTILES_ID_PATTERN, tilejson, name="tilejson"),

    # samples based on data from test fixtures
    url(r'^sample-maps/picker.html?$', SampleMapPicker.as_view()),
    )
