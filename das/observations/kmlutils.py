import logging
import datetime
import zipfile
import dateutil.parser
import pytz
from io import BytesIO

from django.conf import settings
from django.urls import reverse
from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from django.http import Http404
from rest_framework import status
import simplekml

import utils
from utils.drf import StandardResultsSetPagination
from utils.json import zeroout_microseconds
from observations.filters import SubjectObjectPermissionsFilter, create_gp_filter_class
from observations.permissions import StandardObjectPermissions
from observations import models
import observations.serializers as serializers

logger = logging.getLogger(__name__)


def render_to_kmz(content, filename):
    '''
    Render kml string to kmz response.
    :param content: string kml content
    :param filename: filename to include in content-disposition.
    :return: A drf Response
    '''
    full_filename = '{}.kmz'.format(filename)
    zip_io = BytesIO()
    with zipfile.ZipFile(zip_io, mode='w', compression=zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('document.kml', content.encode('utf-8'))
    response = Response(zip_io.getvalue(),
                        content_type='application/vnd.google-earth.kmz')
    response['Content-Disposition'] = 'attachment; filename={}'.format(
        full_filename)
    response['x-das-download-filename'] = full_filename
    response['Content-Length'] = zip_io.tell()
    return response
