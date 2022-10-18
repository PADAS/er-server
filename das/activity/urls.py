from django.conf.urls import re_path
from django.urls import path

from activity import alerts_views, views
from utils.constants import regex

urlpatterns = [
    re_path(r"^events/?$", views.EventsView.as_view(), name="events"),
    re_path(r"^events/geojson/?$", views.EventsGeoJsonView.as_view()),
    re_path(r"^events/export/?$", views.EventsExportView.as_view(),
            name="events-export"),
    re_path(r"^events/schema/?$", views.EventSchemaView.as_view()),
    re_path(
        rf"^events/schema/eventtype/(?P<eventtype>{regex.SLUG})/?$",
        views.EventTypeSchemaView.as_view(),
        name="event-schema-eventtype",
    ),
    re_path(r"^events/count/?$", views.EventCountView.as_view()),
    re_path(r"^events/classes/?$", views.EventClassesView.as_view()),
    re_path(r"^events/factors/?$", views.EventFactorsView.as_view()),
    re_path(
        r"^events/eventtypes/?$", views.EventTypesView.as_view(), name="eventtypes"
    ),
    re_path(
        rf"^events/eventtypes/(?P<eventtype_id>{regex.UUID})/?$",
        views.EventTypeView.as_view(),
        name="eventtype",
    ),
    re_path(
        r"^events/categories/?$",
        views.EventCategoriesView.as_view(),
        name="event-categories",
    ),
    re_path(
        rf"^events/categories/(?P<eventcategory_id>{regex.UUID})/?$",
        views.EventCategoryView.as_view(),
        name="event-category",
    ),
    re_path(r"^events/classfactors/?$", views.EventClassFactorsView.as_view()),
    re_path(r"^events/alerts/targets/?$",
            views.EventAlertTargetsListView.as_view()),
    re_path(
        r"^alerts/conditions/?$",
        alerts_views.EventAlertConditionsListView.as_view(),
        name="alerts-conditions-view",
    ),
    re_path(
        r"^notificationmethods/?$",
        alerts_views.NotificationMethodListView.as_view(),
        name="notificationmethod-list-view",
    ),
    re_path(
        rf"^notificationmethod/(?P<id>{regex.UUID})/?$",
        alerts_views.NotificationMethodView.as_view(),
        name="notificationmethod-view",
    ),
    re_path(
        r"^alerts/?$", alerts_views.AlertRuleListView.as_view(), name="alert-list-view"
    ),
    re_path(
        rf"^alert/(?P<id>{regex.UUID})/?$",
        alerts_views.AlertRuleView.as_view(),
        name="alert-view",
    ),
    re_path(
        rf"^event/(?P<id>{regex.UUID})/?$",
        views.EventView.as_view(),
        name="event-view",
    ),
    re_path(
        r"^eventfilters/?$", views.EventFiltersView.as_view(), name="eventfilters-view"
    ),
    re_path(
        r"^eventfilters/schema/?$",
        views.EventFilterSchemaView.as_view(),
        name="eventfilter-schema-view",
    ),
    re_path(
        r"^eventproviders/?$",
        views.EventProvidersView.as_view(),
        name="eventproviders-view",
    ),
    re_path(
        rf"^eventprovider/(?P<id>{regex.UUID})/?$",
        views.EventProvidersView.as_view(),
        name="eventprovider-view",
    ),
    re_path(
        rf"^eventprovider/(?P<eventprovider_id>{regex.UUID})/eventsources/?$",
        views.EventSourcesView.as_view(),
        name="eventsources-view",
    ),
    re_path(
        rf"^eventprovider/(?P<eventprovider_id>{regex.UUID})/eventsource/(?P<external_event_type>{regex.SLUG})$",
        views.EventSourceView.as_view(),
        name="eventprovider-eventsource-view",
    ),
    re_path(
        rf"^eventsource/(?P<id>{regex.UUID})/?$",
        views.EventSourceView.as_view(),
        name="eventsource-view",
    ),
    re_path(
        rf"^event/(?P<id>{regex.UUID})/state/?$",
        views.EventStateView.as_view(),
        name="event-view-state",
    ),
    re_path(
        rf"^event/(?P<id>{regex.UUID})/notes/?$",
        views.EventNotesView.as_view(),
        name="event-view-notes",
    ),
    re_path(
        rf"^event/(?P<id>{regex.UUID})/note/(?P<note_id>{regex.UUID})/?$",
        views.EventNoteView.as_view(),
        name="event-view-note",
    ),
    re_path(
        rf"^event/(?P<id>{regex.UUID})/files/?$",
        views.EventFilesView.as_view(),
        name="event-view-files",
    ),
    re_path(
        rf"^event/(?P<event_id>{regex.UUID})/file/(?P<filecontent_id>{regex.UUID})/(?P<image_size>{regex.SLUG_20_CHARS})/(?P<filename>.*)?$",
        views.EventFileView.as_view(),
        name="event-view-file-size",
    ),
    re_path(
        rf"^event/(?P<event_id>{regex.UUID})/file/(?P<filecontent_id>{regex.UUID})/(?P<filename>.*)?$",
        views.EventFileView.as_view(),
        name="event-view-file",
    ),
    re_path(
        rf"^event/(?P<from_event_id>{regex.UUID})/relationships/?$",
        views.EventRelationshipsView.as_view(),
        name="event-view-relationships",
    ),
    re_path(
        rf"^event/(?P<from_event_id>{regex.UUID})/relationships/(?P<relationship_type>{regex.SLUG})/?$",
        views.EventRelationshipsView.as_view(),
        name="event-view-filtered-relationships",
    ),
    re_path(
        rf"^event/(?P<from_event_id>{regex.UUID})/relationship/(?P<relationship_type>{regex.SLUG})/(?P<to_event_id>{regex.UUID})/?$",
        views.EventRelationshipView.as_view(),
        name="event-view-relationship",
    ),
    re_path(r"^patrols/types/?$",
            views.PatrolTypesView.as_view(), name="patrol-types"),
    re_path(
        rf"^patrols/types/(?P<id>{regex.UUID})/?$",
        views.PatrolTypeView.as_view(),
        name="patrol-type",
    ),
    re_path(r"^patrols/?$", views.PatrolsView.as_view(), name="patrols"),
    re_path(
        rf"^patrols/(?P<id>{regex.UUID})/?$", views.PatrolView.as_view(), name="patrol"
    ),
    re_path(
        rf"^patrols/(?P<id>{regex.UUID})/notes/?$",
        views.PatrolNotesView.as_view(),
        name="patrol-view-notes",
    ),
    re_path(
        rf"^patrols/(?P<id>{regex.UUID})/notes/(?P<note_id>{regex.UUID})/?$",
        views.PatrolNoteView.as_view(),
        name="patrol-view-note",
    ),
    re_path(
        rf"^patrols/(?P<id>{regex.UUID})/files/?$",
        views.PatrolFilesView.as_view(),
        name="patrol-view-files",
    ),
    re_path(
        rf'^patrols/(?P<id>{regex.UUID})/files/(?P<filecontent_id>{regex.UUID})/(?P<image_size>{regex.SLUG_20_CHARS})/(?P<filename>.*)?$',
        views.PatrolFileView.as_view(), name='patrol-view-file-size'),
    re_path(
        rf"^patrols/(?P<id>{regex.UUID})/file/(?P<filecontent_id>{regex.UUID})/(?P<filename>.*)?$",
        views.PatrolFileView.as_view(),
        name="patrol-view-file",
    ),
    re_path(
        rf"^patrols/(?P<id>{regex.UUID})/file/(?P<filecontent_id>{regex.UUID})/(?P<filename>.*)?$",
        views.PatrolFileView.as_view(),
        name="patrol-view-file",
    ),
    re_path(
        r"^patrols/segments/?$",
        views.PatrolsegmentsView.as_view(),
        name="patrol-segments",
    ),
    re_path(
        r"^patrols/trackedby/?$",
        views.TrackedBySchema.as_view(),
        name="patrol-segments-schema",
    ),
    re_path(
        rf"^patrols/segments/(?P<id>{regex.UUID})/?$",
        views.PatrolsegmentView.as_view(),
        name="patrol-segment",
    ),
    re_path(
        rf"^patrols/segments/(?P<patrol_segment>{regex.UUID})/events/?$",
        views.EventsView.as_view(),
        name="segment-events",
    ),
    re_path(
        rf"^event/(?P<event_id>{regex.UUID})/segments/?$",
        views.PatrolsegmentsView.as_view(),
        name="event-segments-view",
    ),
    path("event/<uuid:event_id>/geometry/",
         views.EventGeometryView.as_view(), name="event-geometries")
]
