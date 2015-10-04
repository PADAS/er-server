from django.conf.urls import patterns, url, include
from django.contrib.auth.decorators import login_required
from mapping.views import *
from mapping.sample_views import *


urlpatterns = patterns(
    'mapping.views',

    url(r'^features/?$', FeatureListJsonView.as_view()),
    url(r'^features/json/?$', FeatureListJsonView.as_view()),
    url(r'^feature/(?P<feature_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/geojson/?$',
        FeatureGeoJsonView.as_view(), name='mapping-feature-geojson'),


    url(r'^base-maps/?$', BaseMapListJsonView.as_view()),
    url(r'^base-maps/json/?$', BaseMapListJsonView.as_view()),
    url(r'^tiles/', include('raster.urls')),

    url(r'^sample-maps/picker.html?$', SampleMapPicker.as_view()),
    )