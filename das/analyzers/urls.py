from __future__ import annotations

from django.urls import re_path
from rest_framework.routers import DefaultRouter

from analyzers.views import (
    EnvironmentalAnalyzerConfigViewSet,
    FeatureProximityAnalyzerConfigViewSet,
    GeofenceAnalyzerConfigViewSet,
    ImmobilityAnalyzerConfigViewSet,
    LowSpeedPercentileAnalyzerConfigViewSet,
    LowSpeedWilcoxAnalyzerConfigViewSet,
    MovementClusterAnalyzerConfigViewSet,
    ObservationAttributeAnalyzerConfigViewSet,
    SpatialAnalyzerListView,
    SubjectAnalyzerListView,
    SubjectProximityAnalyzerConfigViewSet,
)

app_name = "analyzers"

router = DefaultRouter()
router.trailing_slash = "/?"
router.register(r"geofence", GeofenceAnalyzerConfigViewSet, basename="geofence")
router.register(r"featureproximity", FeatureProximityAnalyzerConfigViewSet, basename="featureproximity")
router.register(r"subjectproximity", SubjectProximityAnalyzerConfigViewSet, basename="subjectproximity")
router.register(r"immobility", ImmobilityAnalyzerConfigViewSet, basename="immobility")
router.register(r"environmental", EnvironmentalAnalyzerConfigViewSet, basename="environmental")
router.register(r"lowspeedpercentile", LowSpeedPercentileAnalyzerConfigViewSet, basename="lowspeedpercentile")
router.register(r"lowspeedwilcox", LowSpeedWilcoxAnalyzerConfigViewSet, basename="lowspeedwilcox")
router.register(r"movementcluster", MovementClusterAnalyzerConfigViewSet, basename="movementcluster")
router.register(r"observationattribute", ObservationAttributeAnalyzerConfigViewSet, basename="observationattribute")

urlpatterns = [
    re_path(r"spatial/?$", SpatialAnalyzerListView.as_view(), name="analyzer-spatial-view"),
    re_path(r"subject/?$", SubjectAnalyzerListView.as_view(), name="analyzer-subject-view"),
] + router.urls
