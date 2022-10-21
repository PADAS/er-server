import logging
from datetime import datetime, timedelta
import zipfile
import dateutil.parser
import pytz
from io import BytesIO

import utils
from django.conf import settings
from django.urls import reverse
from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from oauthlib.common import generate_token
from oauth2_provider.models import Application, AccessToken


logger = logging.getLogger(__name__)

KML_TOKEN_TTL_DAYS = getattr(settings, 'KML_TOKEN_TTL_DAYS', 5 * 365)
KML_OAUTH_CLIENT_ID = 'das_kml_export'


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


def get_kml_access_token(user, ttl=KML_TOKEN_TTL_DAYS):

    try:
        app = Application.objects.get(client_id=KML_OAUTH_CLIENT_ID)

        token, created = AccessToken.objects.get_or_create(
            user=user, application=app, scope='read', expires__gt=datetime.now(tz=pytz.utc),
            defaults=dict(expires=datetime.now(tz=pytz.utc) +
                          timedelta(days=ttl), token=generate_token())
        )
        return token.token

    except Application.DoesNotExist:
        logger.error(
            'There exists no Oauth2 Application with client_id %s', KML_OAUTH_CLIENT_ID)


def get_kml_master_link(user, request):

    if user is None:
        user = request.user

    token = get_kml_access_token(user)
    return utils.add_base_url(request,
                              '?'.join((
                                  reverse('subjects-kml-root-view'),
                                  'auth={}'.format(token))
                              )
                              )
