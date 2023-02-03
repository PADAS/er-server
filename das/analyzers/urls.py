from django.urls import re_path

from analyzers.views import SpatialAnalyzerListView, SubjectAnalyzerListView

app_name = "analyzers"

urlpatterns = (
    # a list of available features
    re_path(r"spatial/?$", SpatialAnalyzerListView.as_view(), name="analyzer-spatial-view"),
    re_path(r"subject/?$", SubjectAnalyzerListView.as_view(), name="analyzer-subject-view"),
)
