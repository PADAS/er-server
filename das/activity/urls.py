from django.conf.urls import url, include
from activity import views


urlpatterns = [
    url(r'^events/?$', views.EventsView.as_view()),
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
    url(r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventView.as_view(), name='event-view'),
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
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/photos/?$',
        views.EventPhotosView.as_view(), name='event-view-photos'),
    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/photo/(?P<photo_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventPhotoView.as_view(), name='event-view-photo'),
    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/documents/?$',
        views.EventDocumentsView.as_view(), name='event-view-documents'),
    url(
        r'^event/(?P<event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/document/(?P<document_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventDocumentView.as_view(), name='event-view-document'),
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

