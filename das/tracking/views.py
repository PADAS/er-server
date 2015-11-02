import logging
import datetime

import simplejson as json
import dateutil.parser
import pytz
from django.utils.translation import ugettext_lazy as _
from django.http import Http404, JsonResponse
from django.contrib.auth import get_user_model

import django.views.defaults
from rest_framework import generics
from rest_framework.views import exception_handler
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.compat import set_rollback
import rest_framework.status

from observations import models
import tracking.serializers
import observations.serializers
import copy

class SourceObservationsView(generics.ListCreateAPIView):
    lookup_field = 'id'
    serializer_class = observations.serializers.ObservationSerializer

    def get_queryset(self):
        source = generics.get_object_or_404(models.Source.objects.all(),
                                            id=self.kwargs['id'])
        self.check_object_permissions(self.request, source)
        observations = models.Observation.objects.filter(source=source)
        return observations

    # def get_serializer_context(self):
    #     context = {'request': self.request}
    #     context['show_last_position_date'] = True
    #     return context


    def create(self, request, *args, **kwargs):

        source = generics.get_object_or_404(models.Source.objects.all(),
                                            id=self.kwargs['id'])
        self.check_object_permissions(self.request, source)

        _ = copy.copy(request.data)

        location = _.pop('location')
        _['ts'] = _.pop('recorded_at')

        _.update(location)
        observation = models.Observation.objects.add_observation(source, _)

        # response = JsonResponse(data=dict(message='helo'))
        sd = observations.serializers.ObservationSerializer(observation).data
        return JsonResponse(data=sd)

