from django.urls import re_path

from mapping.spatialviews import (
    SpatialFeatureGroupView,
    SpatialFeatureListView,
    SpatialFeatureTypeListView,
    SpatialFeatureView,
)
from mapping.views import (
    FeatureGeoJsonView,
    FeatureListJsonView,
    FeatureSetGeoJsonView,
    FeatureSetListJsonView,
    LayerJsonView,
    LayerListJsonView,
    MapListJsonView,
    SpatialFeatureTileView,
)
from utils.constants import regex

app_name = "mapping"

urlpatterns = (
    re_path(r"^features/?$", FeatureListJsonView.as_view()),
    # todo:  add caching
    re_path(
        rf"^feature/(?P<id>{regex.UUID})/?$",
        FeatureGeoJsonView.as_view(),
        name="mapping-feature-geojson",
    ),
    re_path(r"^featureset/?$", FeatureSetListJsonView.as_view()),
    # the geojson for a particular feature
    re_path(
        rf"^featureset/(?P<id>{regex.UUID})/?$",
        FeatureSetGeoJsonView.as_view(),
        name="mapping-featureset-geojson",
    ),
    re_path(r"^maps/?$", MapListJsonView.as_view()),
    re_path(r"^layers/?$", LayerListJsonView.as_view()),
    re_path(rf"^layer/(?P<id>{regex.UUID})/?$", LayerJsonView.as_view()),
    re_path(
        rf"^spatialfeaturegroup/(?P<id>{regex.UUID})/?$",
        SpatialFeatureGroupView.as_view(),
        name="spatialfeaturegroup-view",
    ),
    re_path(
        r"^featureclass/?$",
        SpatialFeatureTypeListView.as_view(),
        name="spatialfeaturetype-list",
    ),
    re_path(
        r"^spatialfeature/?$",
        SpatialFeatureListView.as_view(),
        name="spatialfeature-list",
    ),
    re_path(
        rf"^spatialfeature/(?P<id>{regex.UUID})/?$",
        SpatialFeatureView.as_view(),
        name="spatialfeature-detail",
    ),
    # Vector tile endpoint for spatial features
    path(
        "spatialfeatures/tiles/<int:z>/<int:x>/<int:y>.pbf",
        SpatialFeatureTileView.as_view(),
        name="spatialfeature-tiles",
    ),
)
