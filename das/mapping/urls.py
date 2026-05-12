from __future__ import annotations

from django.urls import re_path

from mapping.spatialviews import (
    DeprecatedSpatialFeatureDetailView,
    DeprecatedSpatialFeatureGroupDetailView,
    DeprecatedSpatialFeatureGroupListView,
    DeprecatedSpatialFeatureListView,
    DeprecatedSpatialFeatureTypeDetailView,
    DeprecatedSpatialFeatureTypeListView,
    DisplayCategoryDetailView,
    DisplayCategoryListView,
    SpatialFeatureGroupDetailView,
    SpatialFeatureGroupListView,
    SpatialFeatureTypeDetailView,
    SpatialFeatureTypeListView,
)
from mapping.views import (
    DeprecatedFeatureGeoJsonView,
    DeprecatedFeatureListJsonView,
    DeprecatedFeatureSetGeoJsonView,
    DeprecatedFeatureSetListJsonView,
    DeprecatedLayerJsonView,
    DeprecatedLayerListJsonView,
    DeprecatedMapListJsonView,
    DeprecatedSpatialFeatureTileView,
    LayerJsonView,
    LayerListJsonView,
    MapDetailView,
    MapListJsonView,
)
from utils.constants import regex

app_name = "mapping"

urlpatterns = (
    # Deprecated: use /api/v2.0/features/ instead
    re_path(r"^features/?$", DeprecatedFeatureListJsonView.as_view()),
    # todo:  add caching
    # Deprecated: use /api/v2.0/features/<id>/ instead
    re_path(
        rf"^feature/(?P<id>{regex.UUID})/?$",
        DeprecatedFeatureGeoJsonView.as_view(),
        name="mapping-feature-geojson",
    ),
    re_path(r"^featuregroups/?$", SpatialFeatureGroupListView.as_view(), name="featuregroups-list"),
    re_path(
        rf"^featuregroup/(?P<id>{regex.UUID})/?$",
        SpatialFeatureGroupDetailView.as_view(),
        name="featuregroup-detail",
    ),
    # Deprecated: use /displaycategories/ instead
    re_path(r"^featureset/?$", DeprecatedFeatureSetListJsonView.as_view()),
    re_path(
        rf"^featureset/(?P<id>{regex.UUID})/?$",
        DeprecatedFeatureSetGeoJsonView.as_view(),
        name="mapping-featureset-geojson",
    ),
    re_path(r"^quicklinks/?$", MapListJsonView.as_view(), name="quicklinks-list"),
    re_path(rf"^quicklink/(?P<id>{regex.UUID})/?$", MapDetailView.as_view(), name="quicklink-detail"),
    # Deprecated: use /quicklinks/ instead
    re_path(r"^maps/?$", DeprecatedMapListJsonView.as_view()),
    re_path(r"^basemaps/?$", LayerListJsonView.as_view(), name="basemaps-list"),
    re_path(rf"^basemap/(?P<id>{regex.UUID})/?$", LayerJsonView.as_view(), name="basemap-detail"),
    # Deprecated: use /basemaps/ instead
    re_path(r"^layers/?$", DeprecatedLayerListJsonView.as_view()),
    re_path(rf"^layer/(?P<id>{regex.UUID})/?$", DeprecatedLayerJsonView.as_view()),
    re_path(
        r"^featuretypes/?$",
        SpatialFeatureTypeListView.as_view(),
        name="featuretypes-list",
    ),
    re_path(
        rf"^featuretype/(?P<id>{regex.UUID})/?$",
        SpatialFeatureTypeDetailView.as_view(),
        name="featuretype-detail",
    ),
    # Deprecated: use /featuretypes/ instead
    re_path(r"^featureclass/?$", DeprecatedSpatialFeatureTypeListView.as_view()),
    re_path(rf"^featureclass/(?P<id>{regex.UUID})/?$", DeprecatedSpatialFeatureTypeDetailView.as_view()),
    re_path(
        r"^displaycategories/?$",
        DisplayCategoryListView.as_view(),
        name="displaycategories-list",
    ),
    re_path(
        rf"^displaycategory/(?P<id>{regex.UUID})/?$",
        DisplayCategoryDetailView.as_view(),
        name="displaycategory-detail",
    ),
    # Deprecated: use /featuregroups/ instead
    re_path(
        r"^spatialfeaturegroup/?$",
        DeprecatedSpatialFeatureGroupListView.as_view(),
        name="spatialfeaturegroup-list",
    ),
    re_path(
        rf"^spatialfeaturegroup/(?P<id>{regex.UUID})/?$",
        DeprecatedSpatialFeatureGroupDetailView.as_view(),
        name="spatialfeaturegroup-detail",
    ),
    # Deprecated: use /features/v2/ and /features/v2/<id>/ instead
    re_path(
        r"^spatialfeature/?$",
        DeprecatedSpatialFeatureListView.as_view(),
        name="spatialfeature-list",
    ),
    re_path(
        rf"^spatialfeature/(?P<id>{regex.UUID})/?$",
        DeprecatedSpatialFeatureDetailView.as_view(),
        name="spatialfeature-detail",
    ),
    # Deprecated: use /api/v2.0/features/tiles/ instead
    re_path(
        r"^spatialfeatures/tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)\.pbf$",
        DeprecatedSpatialFeatureTileView.as_view(),
        name="spatialfeature-tiles",
    ),
)
