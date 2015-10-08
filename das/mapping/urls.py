from django.conf.urls import patterns, url, include
from mapping.views import *
from mapping.sample_views import *


urlpatterns = patterns(
    'mapping.views',

    # a list of available features
    url(r'^features/json/?$', FeatureListJsonView.as_view()),
    # todo:  add caching
    url(r'^feature/(?P<feature_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/geojson/?$',
        FeatureGeoJsonView.as_view(), name='mapping-feature-geojson'),

    # a list of available featuresets
    url(r'^featureset/json/?$', FeatureSetListJsonView.as_view()),
    # the geojson for a particular feature
    url(r'^featureset/(?P<featureset_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/geojson/?$',
        FeatureSetGeoJsonView.as_view(), name='mapping-featureset-geojson'),

    # a list of available base maps (from the raster app)
    url(r'^base-maps/json/?$', BaseMapListJsonView.as_view()),

    # samples based on data from test fixtures
    url(r'^sample-maps/picker.html?$', SampleMapPicker.as_view()),
    )