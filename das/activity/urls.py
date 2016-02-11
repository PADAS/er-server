from django.conf.urls import url
from . import views

urlpatterns = [

        # url(r'^source/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/observations/?$',
        #     views.SourceObservationsView.as_view()),
        # url(r'^source/(?P<manufacturer_id>.+)/?$', views.SourceList.as_view()),
        # url(r'^event/(?P<event_id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$', views.event),
        url(r'^events/?$', views.EventsView.as_view()),
        url(r'^event/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$', views.EventView.as_view(), name='event-view'),

]