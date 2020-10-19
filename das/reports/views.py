import os
import pytz
import requests
import datetime
import json
import logging
from collections import Counter

from django.utils import timezone
from django.template.response import TemplateResponse
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from rest_framework import serializers, views, permissions
from django.views.generic.base import TemplateResponseMixin, ContextMixin

from reports.reports import get_daily_report_data

logger = logging.getLogger(__name__)


class ReportDateParameters(serializers.Serializer):
    since = serializers.DateTimeField(default=None)
    before = serializers.DateTimeField(default=None)


class ReportView(views.APIView):
    def dispatch(self, request, report_key, *args, **kwargs):

        if report_key == 'sitrep':
            return SituationReportView().dispatch(request, *args, **kwargs)


class SituationReportView(views.APIView, TemplateResponseMixin, ContextMixin, ):

    permission_classes = (permissions.IsAuthenticated,)

    response_class = TemplateResponse
    # content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    # template_engine = 'docx_template'
    # template_name = 'lewa_sitrep_template.docx'

    def get(self, request, *args, **kwargs):

        qs = ReportDateParameters(data=request.query_params)
        if not qs.is_valid():
            return Response(data=qs.errors, status=status.HTTP_400_BAD_REQUEST)

        qs = qs.validated_data
        now = timezone.now()
        since = qs.get('since') or (now - datetime.timedelta(hours=24))
        before = qs.get('before') or now

        context = self.get_context_data(since=since, before=before, **kwargs)
        return self.render_to_response(context)

    def render_to_response(self, context, **response_kwargs):

        response = super().render_to_response(context, **response_kwargs)
        if 'openxmlformats' in self.content_type:
            response['Content-Disposition'] = 'attachment; filename={}'.format(
                context['report_filename'])
            response['x-das-download-filename'] = context['report_filename']
        return response

    def get_context_data(self, since, before, **kwargs):
        return get_daily_report_data(since, before, **kwargs)


class IsSuperAdminUser(permissions.BasePermission):
    """
    Allows access only to super admin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


def get_sitename():
    server_fqdn = settings.SERVER_FQDN
    name_site = server_fqdn.split('.') if len(server_fqdn.split('.')) > 1 else ''
    return name_site[0]


TABLEAU_VERSION = 3.9


class TableauAPI:

    def __init__(self):
        self.baseURL = f'{settings.TABLEAU_SERVER}/api/{TABLEAU_VERSION}'
        self.username = os.getenv('TABLEAU_API_USERNAME')
        self.password = os.getenv('TABLEAU_API_PASSWORD')
        self.user_id = None
        self.site_id = None
        self.token = None
        self.contenturl = get_sitename() or 'training'
        self.headers = {'content-type': 'application/json', 'accept': 'application/json'}
        self.personal_access_token()

    def personal_access_token(self):
        """
        POST /api/api-version/auth/signin
        """
        f'{self.baseURL}/auth/signin'
        data = {
            "credentials": {
                "name": self.username,
                "password": self.password,
                "site": {
                    'contentUrl': self.contenturl
                }
            }
        }
        response = requests.post(f'{self.baseURL}/auth/signin', json=data, headers=self.headers)
        response = json.loads(response.text)

        error = response.get('error')
        credentials = response.get('credentials')
        if error:
            logger.info(f"Authentication failed with: {error}")
        elif credentials:
            self.user_id = credentials['user'].get('id')
            self.token = credentials['token']
            self.site_id = credentials['site'].get('id')

    def make_get_request(self, path_component):
        self.headers['X-Tableau-Auth'] = f'{self.token}'
        url = f'{self.baseURL}/{path_component}'
        response = requests.get(url, headers=self.headers)
        return response

    def get_views_site(self, site_id):
        """
        Returns all the views for the specified site.
        GET /api/api-version/sites/site-id/views?pageSize=page-size&pageNumber=page-number
        """
        path = f'sites/{site_id}/views?pageSize=1000'
        response = self.make_get_request(path)
        return response.text

    def get_workbook(self, site_id, workbook_id):
        """
        Returns information about the specified workbook, including information about views and tags.
        GET /api/api-version/sites/site-id/workbooks/workbook-id
        """
        path = f'sites/{site_id}/workbooks/{workbook_id}'
        response = self.make_get_request(path)
        return response.text

    def get_view_specific_view(self, site_id, view_id):
        """
        Gets the details of a specific view.
        GET /api/api-version/sites/site-id/views/view-id
        """
        path = f'sites/{site_id}/views/{view_id}'
        response = self.make_get_request(path)
        return response.text

    def get_site(self, site_id):
        """
        Returns information about the specified site,
        GET /api/api-version/sites/site-id
        """
        path = f'sites/{site_id}'
        response = self.make_get_request(path)
        return response.text


class TableauView(views.APIView):
    permission_classes = (IsSuperAdminUser,)

    def get(self, request, *args, **kwargs):
        view_id = kwargs.get('view_id')
        instance = TableauAPI()
        site_id = instance.site_id

        response = json.loads(instance.get_view_specific_view(site_id, view_id))

        view = response.get('view')
        if not view:
            return Response(response)

        workbook_id = view['workbook'].get('id')
        view_urlname = view.get('viewUrlName') if view else None

        response = json.loads(instance.get_workbook(site_id, workbook_id))
        site_response = json.loads(instance.get_site(site_id))
        site_name = site_response['site']['name']
        workbook_contenturl = response['workbook']['contentUrl']

        ticket = self.get_ticket()
        if ticket == '-1':
            data = {'ticket': ticket, 'status': 'failed to retrieve tableau ticket'}
            return Response(data)
        else:
            url = f'{settings.TABLEAU_SERVER}/trusted/{ticket}/t/{site_name}/views/{workbook_contenturl}/{view_urlname}'
            response = {'ticket': ticket, 'display_url': url}

        return Response(response)

    @staticmethod
    def get_ticket():
        site_name = get_sitename()
        username = f'{site_name}_tableau_user'
        data = {'username': username, 'target_site': get_sitename()}
        response = requests.post(url=f'{settings.TABLEAU_SERVER}/trusted', data=data)
        return response.text


class TableauAPIView(views.APIView):
    permission_classes = (IsSuperAdminUser,)

    def get(self, request, *args, **kwargs):
        instance = TableauAPI()
        site_id = instance.site_id
        sites = json.loads(instance.get_views_site(site_id))
        return Response(sites)

