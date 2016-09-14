from django.conf.urls import url, include
from activity import views


urlpatterns = [
    url(r'^events/?$', views.EventsView.as_view()),
    url(r'^events/schema/?$', views.EventSchemaView.as_view()),
    url(r'^events/schema/eventtype/(?P<eventtype>[a-z0-9-_]+)?$', views.EventTypeSchemaView.as_view()),
    url(r'^events/count/?$', views.EventCountView.as_view()),
    url(r'^events/classes/?$', views.EventClassesView.as_view()),
    url(r'^events/factors/?$', views.EventFactorsView.as_view()),
    url(r'^events/classfactors/?$', views.EventClassFactorsView.as_view()),
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
    # url(
    #     r'^event/photos/?$', views.EventPhotoView.as_view(), name='event-photo'),
]

