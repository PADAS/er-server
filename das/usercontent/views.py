from django.shortcuts import render
from collections import OrderedDict
from datetime import timedelta

from rest_framework import generics, status, response
from django.db.models import Prefetch
from django.core.urlresolvers import reverse
from django.template import Template, Context

import rest_framework.exceptions
from rest_framework_extensions.etag.decorators import etag

from activity.models import Event, EventNote, EventPhoto, EventClass,\
    EventFactor, EventClassFactor, EventType, EventRelationship, EventCategory
from activity.serializers import EventSerializer, EventNoteSerializer,\
    EventJSONSchema, EventStateSerializer, EventPhotoSerializer,\
    EventClassSerializer, EventFactorSerializer, EventClassFactorSerializer,\
    EventTypeSerializer, EventRelationshipSerializer, EventCategorySerializer

from activity.alerts import get_alert_users
from activity.filters import EventObjectPermissionsFilter
from activity.permissions import EventCategoryPermissions, EventObjectPermissions
from utils.drf import StandardResultsSetPagination
from utils.json import parse_bool, loads
import utils
from activity import schema_utils
import accounts.serializers
import accounts.models

from usercontent.serializers import FileContentSerializer

class FileContentView(generics.RetrieveUpdateDestroyAPIView):
    # permission_classes = (EventCategoryPermissions,)
    serializer_class = FileContentSerializer

    # def get_queryset(self):
    #     event = generics.get_object_or_404(Event.objects.all(),
    #                                        pk=self.kwargs['id'])
    #
    #     photos = EventPhoto.objects.all().filter(event=event)
    #     return photos
    #
    # def get_object(self):
    #     queryset = self.get_queryset()
    #     filters = {'id': self.kwargs['photo_id']}
    #
    #     obj = generics.get_object_or_404(queryset, **filters)
    #
    #     return obj
