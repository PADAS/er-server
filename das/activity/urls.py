from django.conf.urls import url
from . import views


urlpatterns = [
    url(r'^events/?$', views.EventsView.as_view()),
    url(r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventView.as_view(), name='event-view'),
    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/notes/?$',
        views.EventNotesView.as_view(), name='event-view-notes'),
    url(
        r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/note/(?P<note_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.EventNoteView.as_view(), name='event-view-note'),
]
