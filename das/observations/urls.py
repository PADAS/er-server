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
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns

from observations import views

urlpatterns = [
    url(r'^regions/?$', views.RegionsView.as_view()),
    url(r'^region/(?P<slug>[a-z0-9-]+)/?$', views.RegionView.as_view()),

    url(r'^subjects/kml/?$', views.KmlSubjectsView.as_view(),
        name='subjects-kml-view'),

    # TODO: This responds with the user-level doc with a single network-link. Jake prefers we produce this file
    # and email it to user (rather than producing it in the API).
    url(r'^subjects/kml/root/?$', views.KmlRootView.as_view(),
        name='subjects-kml-root-view'),

    url(r'^region/(?P<slug>[a-z0-9-]+)/subjects/?$',
        views.RegionSubjectsView.as_view()),

    url(r'^subjects/geojson/?$', views.SubjectsGeoJsonView.as_view(),
        name='subjects-geojson-view'),

    url(r'^subjects/?$', views.SubjectsView.as_view(), name="subjects-list-view"),
    url(r'^subject/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.SubjectView.as_view(), name='subject-view'),
    url(r'^subject/(?P<subject_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/tracks/?$',
        views.SubjectTracksView.as_view(), name='subject-view-tracks'),
    url(r'^subject/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/subjectsources/?$',
        views.SubjectSubjectSourcesView.as_view()),
    url(r'^subject/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/sources/?$',
        views.SubjectSourcesView.as_view()),
    url(r'^subject/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/source/(?P<source_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$', views.SubjectSourceView.as_view()),
    url(r'^subject/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/source/(?P<source_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/tracks/?$', views.SubjectSourceTrackView.as_view()),

    url(
        r'^subject/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/kml/?$',
        views.KmlSubjectView.as_view(), name='subject-kml-view'),

    url(r'^subject/(?P<subject_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/status/?$',
        views.SubjectStatusView.as_view(), name='subjectstatus-view'),


    url(r'^sources/?$', views.SourcesView.as_view(), name='sources-view'),
    url(r'^source/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.SourceView.as_view(), name='source-view'),
    url(r'^source/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/subjects/?$',
        views.SourceSubjectsView.as_view(), name='source-subjects-view'),
    url(r'^source/(?P<manufacturer_id>[0-9a-zA-Z\-\.]{1,80})/?$',
        views.SourceView.as_view()),
    url(r'^source/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/gpxdata/?$',
        views.GPXFileUploadView.as_view(), name='gpx-upload'),
    url(r'^source/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/gpxdata/status/(?P<task_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.GPXTaskStatusView.as_view(), name='gpx-status'),
    url(r'^observation/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.ObservationView.as_view(), name="observation-view"),
    url(r'^observations/?$', views.ObservationsView.as_view(),
        name="observations-list-view"),
    url(r'^subjectgroups/?$', views.SubjectGroupsView.as_view()),
    url(r'^subjectgroup/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.SubjectGroupView.as_view()),
    url(r'^sourcegroups/?$', views.SourceGroupsView.as_view()),
    url(r'^sourceproviders/?$', views.SourceProvidersView.as_view()),
    url(r'^sourceprovider/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.SourceProvidersViewPartial.as_view()),
    url(r'^trackingdata/export/?$', views.TrackingDataCsvView.as_view()),
    url(r'^trackingmetadata/export/?$',
        views.TrackingMetaDataExportView.as_view()),
    url(r'^sourcegroup/(?P<slug>[a-zA-Z0-9\w\W\s\S-]+)/?$',
        views.SourceGroupView.as_view()),
    url(r'^messages/?$', views.MessagesView.as_view(), name="messages-view"),
    url(r'^messages/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.MessageView.as_view()),
    url(r'^news/?$', views.AnnouncementsView.as_view(), name="news-view",),

    url(r'^subjectsources/?$', views.SubjectSourcesAssignmentView.as_view(),
        name='subject-sources-list-view'),

]

urlpatterns = format_suffix_patterns(urlpatterns)
