from django.urls import path, re_path

from mapping.spatialviews import SpatialFeatureGroupView, SpatialFeatureView
from mapping.views import (FeatureGeoJsonView, FeatureListJsonView,
                           FeatureSetGeoJsonView, FeatureSetListJsonView,
                           LayerJsonView, LayerListJsonView, MapListJsonView)

app_name = "mapping"

urlpatterns = (
    path("features/", FeatureListJsonView.as_view()),
    # todo:  add caching
    re_path(
        r"^feature/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$",
        FeatureGeoJsonView.as_view(),
        name="mapping-feature-geojson",
    ),
    path("featureset/", FeatureSetListJsonView.as_view()),
    # the geojson for a particular feature
    re_path(
        r"^featureset/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$",
        FeatureSetGeoJsonView.as_view(),
        name="mapping-featureset-geojson",
    ),
    path("maps/", MapListJsonView.as_view()),
    path("layers/", LayerListJsonView.as_view()),
    path("layer/<uuid:id>/", LayerJsonView.as_view()),
    path(
        "spatialfeaturegroup/<uuid:id>/",
        SpatialFeatureGroupView.as_view(),
        name="spatialfeaturegroup-view",
    ),
    path(
        "spatialfeature/<uuid:id>/",
        SpatialFeatureView.as_view(),
        name="spatialfeature-view",
    ),
)
