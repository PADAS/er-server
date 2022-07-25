from django.conf.urls import re_path
from django.urls import path

from activity import alerts_views, views

urlpatterns = [
    path("events/", views.EventsView.as_view(), name="events"),
    path("events/geojson/", views.EventsGeoJsonView.as_view()),
    path("events/export/", views.EventsExportView.as_view()),
    path("events/schema/", views.EventSchemaView.as_view()),
    path(
        "events/schema/eventtype/<slug:eventtype>/",
        views.EventTypeSchemaView.as_view(),
        name="event-schema-eventtype",
    ),
    path("events/count/", views.EventCountView.as_view()),
    path("events/classes/", views.EventClassesView.as_view()),
    path("events/factors/", views.EventFactorsView.as_view()),
    path("events/eventtypes/", views.EventTypesView.as_view(), name="eventtypes"),
    path(
        "events/eventtypes/<uuid:eventtype_id>/",
        views.EventTypeView.as_view(),
        name="eventtype",
    ),
    path(
        "events/categories/",
        views.EventCategoriesView.as_view(),
        name="event-categories",
    ),
    path(
        "events/categories/<uuid:eventcategory_id>/",
        views.EventCategoryView.as_view(),
        name="event-category",
    ),
    path("events/classfactors/", views.EventClassFactorsView.as_view()),
    path("events/alerts/targets/", views.EventAlertTargetsListView.as_view()),
    path(
        "alerts/conditions/",
        alerts_views.EventAlertConditionsListView.as_view(),
        name="alerts-conditions-view",
    ),
    path(
        "notificationmethods/",
        alerts_views.NotificationMethodListView.as_view(),
        name="notificationmethod-list-view",
    ),
    path(
        "notificationmethod/<uuid:id>/",
        alerts_views.NotificationMethodView.as_view(),
        name="notificationmethod-view",
    ),
    path("alerts/", alerts_views.AlertRuleListView.as_view(), name="alert-list-view"),
    path("alert/<uuid:id>/", alerts_views.AlertRuleView.as_view(), name="alert-view"),
    path("event/<uuid:id>/", views.EventView.as_view(), name="event-view"),

    path("eventfilters/", views.EventFiltersView.as_view(),
         name="eventfilters-view"),
    path(
        "eventfilters/schema/",
        views.EventFilterSchemaView.as_view(),
        name="eventfilter-schema-view",
    ),
    path(
        "eventproviders/",
        views.EventProvidersView.as_view(),
        name="eventproviders-view",
    ),
    path(
        "eventprovider/<uuid:id>[0-9a-fA-F]/",
        views.EventProvidersView.as_view(),
        name="eventprovider-view",
    ),
    path(
        r"eventprovider/<uuid:eventprovider_id>/eventsources/",
        views.EventSourcesView.as_view(),
        name="eventsources-view",
    ),
    path(
        "eventprovider/<uuid:eventprovider_id>/eventsource/<slug:external_event_type>/",
        views.EventSourceView.as_view(),
        name="eventprovider-eventsource-view",
    ),
    path(
        "eventsource/<uuid:id>/",
        views.EventSourceView.as_view(),
        name="eventsource-view",
    ),
    path(
        "event/<uuid:id>/state/",
        views.EventStateView.as_view(),
        name="event-view-state",
    ),
    path(
        "event/<uuid:id>/notes/",
        views.EventNotesView.as_view(),
        name="event-view-notes",
    ),
    path(
        "event/<uuid:id>/note/<uuid:note_id>/",
        views.EventNoteView.as_view(),
        name="event-view-note",
    ),
    path(
        "event/<uuid:id>/files/",
        views.EventFilesView.as_view(),
        name="event-view-files",
    ),
    re_path(
        r"^event/(?P<event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/file/(?P<filecontent_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/(?P<image_size>[a-zA-Z0-9]{1,20})/(?P<filename>.*)?$",
        views.EventFileView.as_view(),
        name="event-view-file-size",
    ),
    path(
        r"event/<uuid:event_id>/file/<uuid:filecontent_id>/",
        views.EventFileView.as_view(),
        name="event-view-file",
    ),
    path(
        r"event/<uuid:event_id>/file/<uuid:filecontent_id>/<str:filename>/",
        views.EventFileView.as_view(),
        name="event-view-file",
    ),
    path(
        "event/<uuid:from_event_id>/relationships/",
        views.EventRelationshipsView.as_view(),
        name="event-view-relationships",
    ),
    path(
        "event/<uuid:from_event_id>/relationships/<slug:relationship_type>/",
        views.EventRelationshipsView.as_view(),
        name="event-view-filtered-relationships",
    ),
    path(
        "event/<uuid:from_event_id>/relationship/<slug:relationship_type>/<uuid:to_event_id>/",
        views.EventRelationshipView.as_view(),
        name="event-view-relationship",
    ),
    path("patrols/types/", views.PatrolTypesView.as_view(), name="patrol-types"),
    path(
        "patrols/types/<uuid:id>/", views.PatrolTypeView.as_view(), name="patrol-type"
    ),
    path("patrols/", views.PatrolsView.as_view(), name="patrols"),
    path("patrols/<uuid:id>/", views.PatrolView.as_view(), name="patrol"),
    path(
        "patrols/<uuid:id>/notes/",
        views.PatrolNotesView.as_view(),
        name="patrol-view-notes",
    ),
    path(
        "patrols/<uuid:id>/notes/<uuid:note_id>/",
        views.PatrolNoteView.as_view(),
        name="patrol-view-note",
    ),
    path(
        "patrols/<uuid:id>/files/",
        views.PatrolFilesView.as_view(),
        name="patrol-view-files",
    ),
    re_path(
        r"^patrols/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/files/(?P<filecontent_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/(?P<image_size>[a-zA-Z0-9]{1,20})/(?P<filename>.*)?$",
        views.PatrolFileView.as_view(),
        name="patrol-view-file-size",
    ),
    path(
        "patrols/<uuid:id>/file/<uuid:filecontent_id>/",
        views.PatrolFileView.as_view(),
        name="patrol-view-file",
    ),
    path(
        "patrols/<uuid:id>/file/<uuid:filecontent_id>/<str:filename>/",
        views.PatrolFileView.as_view(),
        name="patrol-view-file",
    ),
    path(
        "patrols/segments/", views.PatrolsegmentsView.as_view(), name="patrol-segments"
    ),
    path(
        "patrols/trackedby/",
        views.TrackedBySchema.as_view(),
        name="patrol-segments-schema",
    ),
    path(
        "patrols/segments/<uuid:id>/",
        views.PatrolsegmentView.as_view(),
        name="patrol-segment",
    ),
    path(
        "patrols/segments/<uuid:patrol_segment>/events/",
        views.EventsView.as_view(),
        name="segment-events",
    ),
    path(
        "event/<uuid:event_id>/segments/",
        views.PatrolsegmentsView.as_view(),
        name="event-segments-view",
    ),
]
