from __future__ import annotations

from django.urls import re_path

from mapping.spatialviews import SpatialFeatureDetailView, SpatialFeatureListView
from mapping.views import SpatialFeatureTileView
from utils.constants import regex

app_name = "mapping_v2"

urlpatterns = (
    re_path(r"^features/?$", SpatialFeatureListView.as_view(), name="feature-list"),
    re_path(
        rf"^feature/(?P<id>{regex.UUID})/?$",
        SpatialFeatureDetailView.as_view(),
        name="feature-detail",
    ),
    re_path(
        r"^features/tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)\.pbf$",
        SpatialFeatureTileView.as_view(),
        name="feature-tiles",
    ),
)
