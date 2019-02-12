from django.conf.urls import url, include
from activity import views

urlpatterns = [
    url(r'^events/?$', views.EventsView.as_view()),
    url(r'^events/export/?$', views.EventsExportView.as_view(
        content_type='text/csv',
        template_engine='jinja2',
        template_name='event_export_template.html')),
    url(r'^events/schema/?$', views.EventSchemaView.as_view()),
    url(r'^events/schema/eventtype/(?P<eventtype>[a-z0-9-_]+)?$',
        views.EventTypeSchemaView.as_view(), name='event-schema-eventtype'),
    url(r'^events/count/?$', views.EventCountView.as_view()),
    url(r'^events/classes/?$', views.EventClassesView.as_view()),
    url(r'^events/factors/?$', views.EventFactorsView.as_view()),
    url(r'^events/eventtypes/?$', views.EventTypesView.as_view()),
    url(r'^events/categories/?$', views.EventCategoriesView.as_view()),
    url(r'^events/classfactors/?$', views.EventClassFactorsView.as_view()),
    url(r'^events/alerts/targets/?$', views.EventAlertTargetsListView.as_view()),

    url(r'^alerts/conditions/?$', views.EventAlertConditionsListView.as_view(),
        name='alerts-conditions-view'),

    url(r'^notificationmethods/?$',
        views.NotificationMethodListView.as_view(),
        name='notificationmethod-list-view'),

    url(r'^notificationmethod/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.NotificationMethodView.as_view(),
        name='notificationmethod-view'),

    url(r'^alerts/?$',
        views.AlertRuleListView.as_view(),
        name='alert-list-view'),

    url(r'^alert/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.AlertRuleView.as_view(),
        name='alert-view'),

    url(r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventView.as_view(), name='event-view'),
    url(r'^eventfilters/?$',
        views.EventFiltersView.as_view(), name='eventfilters-view'),
    url(r'^eventfilters/schema?$',
        views.EventFilterSchemaView.as_view(), name='eventfilter-schema-view'),

    url(r'^eventproviders/?$',
        views.EventProvidersView.as_view(), name='eventproviders-view'),
    url(r'^eventprovider/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventProvidersView.as_view(), name='eventprovider-view'),

    url(
        r'^eventprovider/(?P<eventprovider_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/eventsources/?$',
        views.EventSourcesView.as_view(), name='eventsources-view'),

    url(r'^eventprovider/(?P<eventprovider_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/eventsource/(?P<external_event_type>[0-9a-zA-Z_-]+)$',
        views.EventSourceView.as_view(), name='eventprovider-eventsource-view'),
    url(r'^eventsource/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventSourceView.as_view(), name='eventsource-view'),

    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/state/?$',
        views.EventStateView.as_view(), name='event-view-state'),
    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/notes/?$',
        views.EventNotesView.as_view(), name='event-view-notes'),
    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/note/(?P<note_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventNoteView.as_view(), name='event-view-note'),
    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/files/?$',
        views.EventFilesView.as_view(), name='event-view-files'),
    url(
        r'^event/(?P<event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/file/(?P<filecontent_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/(?P<image_size>[a-zA-Z0-9]{1,20})/(?P<filename>.*)?$',
        views.EventFileView.as_view(), name='event-view-file-size'),
    url(
        r'^event/(?P<event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/file/(?P<filecontent_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/(?P<filename>.*)?$',
        views.EventFileView.as_view(), name='event-view-file'),
    url(
        r'^event/(?P<from_event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/relationships/?$',
        views.EventRelationshipsView.as_view(), name='event-view-relationships'),
    url(
        r'^event/(?P<from_event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/relationships/(?P<relationship_type>[0-9a-zA-Z_]+)/?$',
        views.EventRelationshipsView.as_view(), name='event-view-filtered-relationships'),
    url(
        r'^event/(?P<from_event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/relationship/(?P<relationship_type>[0-9a-zA-Z_]+)/(?P<to_event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventRelationshipView.as_view(), name='event-view-relationship'),
]
