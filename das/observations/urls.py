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
from django.urls import re_path
from rest_framework.urlpatterns import format_suffix_patterns

from observations import views
from utils.constants import regex

urlpatterns = [
    re_path(r"^regions/?$", views.RegionsView.as_view()),
    re_path(r"^region/(?P<slug>[a-z0-9-]+)/?$", views.RegionView.as_view()),
    re_path(
        r"^subjects/kml/?$", views.KmlSubjectsView.as_view(), name="subjects-kml-view"
    ),
    # TODO: This responds with the user-level doc with a single network-link. Jake prefers we produce this file
    # and email it to user (rather than producing it in the API).
    re_path(
        r"^subjects/kml/root/?$",
        views.KmlRootView.as_view(),
        name="subjects-kml-root-view",
    ),
    re_path(
        r"^region/(?P<slug>[a-z0-9-]+)/subjects/?$", views.RegionSubjectsView.as_view()
    ),
    re_path(
        r"^subjects/geojson/?$",
        views.SubjectsGeoJsonView.as_view(),
        name="subjects-geojson-view",
    ),
    re_path(r"^subjects/?$", views.SubjectsView.as_view(),
            name="subjects-list-view"),
    re_path(
        rf"^subject/(?P<id>{regex.UUID})/?$",
        views.SubjectView.as_view(),
        name="subject-view",
    ),
    re_path(
        rf"^subject/(?P<subject_id>{regex.UUID})/tracks/?$",
        views.SubjectTracksView.as_view(),
        name="subject-view-tracks",
    ),
    re_path(
        rf"^subject/(?P<id>{regex.UUID})/subjectsources/?$",
        views.SubjectSubjectSourcesView.as_view(),
    ),
    re_path(
        rf"^subject/(?P<id>{regex.UUID})/sources/?$", views.SubjectSourcesView.as_view()
    ),
    re_path(
        rf"^subject/(?P<id>{regex.UUID})/source/(?P<source_id>{regex.UUID})/?$",
        views.SubjectSourceView.as_view(),
    ),
    re_path(
        rf"^subject/(?P<id>{regex.UUID})/source/(?P<source_id>{regex.UUID})/tracks/?$",
        views.SubjectSourceTrackView.as_view(),
    ),
    re_path(
        rf"^subject/(?P<id>{regex.UUID})/kml/?$",
        views.KmlSubjectView.as_view(),
        name="subject-kml-view",
    ),
    re_path(
        rf"^subject/(?P<subject_id>{regex.UUID})/status/?$",
        views.SubjectStatusView.as_view(),
        name="subjectstatus-view",
    ),
    re_path(rf"^sources/?$", views.SourcesView.as_view(), name="sources-view"),
    re_path(
        rf"^source/(?P<id>{regex.UUID})/?$",
        views.SourceView.as_view(),
        name="source-view",
    ),
    re_path(
        rf"^source/(?P<id>{regex.UUID})/subjects/?$",
        views.SourceSubjectsView.as_view(),
        name="source-subjects-view",
    ),
    re_path(
        r"^source/(?P<manufacturer_id>[0-9a-zA-Z\-\.]{1,80})/?$",
        views.SourceView.as_view(),
    ),
    re_path(
        rf"^source/(?P<id>{regex.UUID})/gpxdata/?$",
        views.GPXFileUploadView.as_view(),
        name="gpx-upload",
    ),
    re_path(
        rf"^source/(?P<id>{regex.UUID})/gpxdata/status/(?P<task_id>{regex.UUID})/?$",
        views.GPXTaskStatusView.as_view(),
        name="gpx-status",
    ),
    re_path(
        rf"^observation/(?P<id>{regex.UUID})/?$",
        views.ObservationView.as_view(),
        name="observation-view",
    ),
    re_path(
        r"^observations/?$",
        views.ObservationsView.as_view(),
        name="observations-list-view",
    ),
    re_path(r"^subjectgroups/?$", views.SubjectGroupsView.as_view()),
    re_path(
        rf"^subjectgroup/(?P<id>{regex.UUID})/?$", views.SubjectGroupView.as_view()
    ),
    re_path(r"^sourcegroups/?$", views.SourceGroupsView.as_view()),
    re_path(r"^sourceproviders/?$", views.SourceProvidersView.as_view()),
    re_path(
        rf"^sourceprovider/(?P<id>{regex.UUID})/?$",
        views.SourceProvidersViewPartial.as_view(),
    ),
    re_path(r"^trackingdata/export/?$", views.TrackingDataCsvView.as_view()),
    re_path(r"^trackingmetadata/export/?$",
            views.TrackingMetaDataExportView.as_view()),
    re_path(
        r"^sourcegroup/(?P<slug>[a-zA-Z0-9\w\W\s\S-]+)/?$",
        views.SourceGroupView.as_view(),
    ),
    re_path(r"^messages/?$", views.MessagesView.as_view(), name="messages-view"),
    re_path(rf"^messages/(?P<id>{regex.UUID})/?$",
            views.MessageView.as_view()),
    re_path(
        r"^news/?$",
        views.AnnouncementsView.as_view(),
        name="news-view",
    ),
    re_path(
        r"^subjectsources/?$",
        views.SubjectSourcesAssignmentView.as_view(),
        name="subject-sources-list-view",
    ),
]

urlpatterns = format_suffix_patterns(urlpatterns)
