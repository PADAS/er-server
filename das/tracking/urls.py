from django.conf.urls import url
from tracking import views

urlpatterns = [
        url(r'^source/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/observations/?$',
            views.SourceObservationsView.as_view()),

]