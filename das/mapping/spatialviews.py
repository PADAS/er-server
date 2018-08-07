import simplejson as json
import logging
from itertools import chain
import hashlib

from django.core.serializers import serialize
from django.urls import reverse
from django.http import HttpResponse, Http404
from django.utils.translation import ugettext_lazy as _
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from rest_framework_extensions.etag.decorators import etag

from mapping.models import PolygonFeature, LineFeature, PointFeature, SpatialFeatureGroupStatic
from mapping.models import MBTiles, MBTilesNotFoundError, MissingTileError, Map
import mapping.serializers as serializers
from mapping import app_settings

logger = logging.getLogger(__name__)


class SpatialFeatureGroupView(generics.RetrieveAPIView):

    serializer_class = serializers.SpatialFeatureGroupStaticSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return SpatialFeatureGroupStatic.objects.all()
