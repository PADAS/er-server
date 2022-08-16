"""api URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  re_path(r'^blog/', include(blog_urls))
"""
from django.conf.urls import re_path
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from observations import views

urlpatterns = [
    path("regions/", views.RegionsView.as_view()),
    path("region/<slug:slug>/", views.RegionView.as_view()),
    path("subjects/kml/", views.KmlSubjectsView.as_view(),
         name="subjects-kml-view"),
    # TODO: This responds with the user-level doc with a single network-link. Jake prefers we produce this file
    # and email it to user (rather than producing it in the API).
    path(
        "subjects/kml/root/", views.KmlRootView.as_view(), name="subjects-kml-root-view"
    ),
    path("region/<slug:slug>/subjects/", views.RegionSubjectsView.as_view()),
    path(
        "subjects/geojson/",
        views.SubjectsGeoJsonView.as_view(),
        name="subjects-geojson-view",
    ),
    path("subjects/", views.SubjectsView.as_view(), name="subjects-list-view"),
    path("subject/<uuid:id>/", views.SubjectView.as_view(), name="subject-view"),
    path(
        "subject/<uuid:subject_id>/tracks/",
        views.SubjectTracksView.as_view(),
        name="subject-view-tracks",
    ),
    path(
        "subject/<uuid:id>/subjectsources/", views.SubjectSubjectSourcesView.as_view()
    ),
    path("subject/<uuid:id>/sources/", views.SubjectSourcesView.as_view()),
    path(
        "subject/<uuid:id>/source/<uuid:source_id>/", views.SubjectSourceView.as_view()
    ),
    path(
        "subject/<uuid:id>/source/<uuid:source_id>/tracks/",
        views.SubjectSourceTrackView.as_view(),
    ),
    path(
        "subject/<uuid:id>/kml/",
        views.KmlSubjectView.as_view(),
        name="subject-kml-view",
    ),
    path(
        "subject/<uuid:subject_id>/status/",
        views.SubjectStatusView.as_view(),
        name="subjectstatus-view",
    ),
    path("sources/", views.SourcesView.as_view(), name="sources-view"),
    path("source/<uuid:id>/", views.SourceView.as_view(), name="source-view"),
    path(
        "source/<uuid:id>/subjects/",
        views.SourceSubjectsView.as_view(),
        name="source-subjects-view",
    ),
    re_path(
        r"^source/(?P<manufacturer_id>[0-9a-zA-Z\-\.]{1,80})/$",
        views.SourceView.as_view(),
    ),
    path(
        "source/<uuid:id>/gpxdata/",
        views.GPXFileUploadView.as_view(),
        name="gpx-upload",
    ),
    path(
        "source/<uuid:id>/gpxdata/status/<uuid:task_id>/",
        views.GPXTaskStatusView.as_view(),
        name="gpx-status",
    ),
    path(
        "observation/<uuid:id>/",
        views.ObservationView.as_view(),
        name="observation-view",
    ),
    path(
        "observations/", views.ObservationsView.as_view(), name="observations-list-view"
    ),
    path("subjectgroups/", views.SubjectGroupsView.as_view()),
    path("subjectgroup/<uuid:id>/", views.SubjectGroupView.as_view()),
    path("sourcegroups/", views.SourceGroupsView.as_view()),
    path("sourceproviders/", views.SourceProvidersView.as_view()),
    path("sourceprovider/<uuid:id>/", views.SourceProvidersViewPartial.as_view()),
    path("trackingdata/export/", views.TrackingDataCsvView.as_view()),
    path("trackingmetadata/export/", views.TrackingMetaDataExportView.as_view()),
    path("sourcegroup/<slug:slug>/", views.SourceGroupView.as_view()),
    path("messages/", views.MessagesView.as_view(), name="messages-view"),
    path("messages/<uuid:id>/", views.MessageView.as_view()),
    path(
        "news/",
        views.AnnouncementsView.as_view(),
        name="news-view",
    ),
    path(
        "subjectsources/",
        views.SubjectSourcesAssignmentView.as_view(),
        name="subject-sources-list-view",
    ),
]

urlpatterns = format_suffix_patterns(urlpatterns)
