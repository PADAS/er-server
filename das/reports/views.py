import requests
import datetime
import json
import logging

import requests
from django.conf import settings
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.generic.base import TemplateResponseMixin, ContextMixin
from rest_framework import generics
from rest_framework import status, serializers
from rest_framework import views, permissions
from rest_framework.response import Response

from core.utils import get_site_name
from reports.reports import get_daily_report_data
from activity.permissions import EventCategoryPermissions
from activity.models import EventCategory

logger = logging.getLogger(__name__)


class ReportDateParameters(serializers.Serializer):
    since = serializers.DateTimeField(default=None)
    before = serializers.DateTimeField(default=None)


class ReportView(views.APIView):
    def dispatch(self, request, report_key, *args, **kwargs):

        if report_key == 'sitrep':
            return SituationReportView().dispatch(request, *args, **kwargs)


class SituationReportView(views.APIView, TemplateResponseMixin, ContextMixin, ):

    def get_template_names(self):
        '''
        Favor a report template in a sub-folder named for the site's domain name.
        Fall back to 'default'.
        :return: a list of "template names".
        '''
        return [f'{folder}/daily_report_template.docx' for folder in
                (settings.DAILY_REPORT_TEMPLATE_SUBFOLDER, 'default')]

    permission_classes = (permissions.IsAuthenticated,)

    response_class = TemplateResponse
    # content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    # template_engine = 'docx_template'
    # template_name = 'lewa_sitrep_template.docx'

    def get_permitted_event_categories(self, request):
        permitted_categories = []

        for category in EventCategory.objects.filter(is_active=True):
            permission_name = 'activity.{0}_{1}'.format(
                category.value,
                EventCategoryPermissions.http_method_map['GET']
            )
            if request.user.has_perm(permission_name):
                permitted_categories.append(category)
        return permitted_categories


    def get(self, request, *args, **kwargs):

        qs = ReportDateParameters(data=request.query_params)
        if not qs.is_valid():
            return Response(data=qs.errors, status=status.HTTP_400_BAD_REQUEST)

        qs = qs.validated_data
        now = timezone.now()
        since = qs.get('since') or (now - datetime.timedelta(hours=24))
        before = qs.get('before') or now

        event_categories = self.get_permitted_event_categories(request)
        context = self.get_context_data(since=since, before=before, event_categories=event_categories,
                                        **kwargs)
        return self.render_to_response(context)

    def render_to_response(self, context, **response_kwargs):

        response = super().render_to_response(context, **response_kwargs)
        if 'openxmlformats' in self.content_type:
            response['Content-Disposition'] = 'attachment; filename={}'.format(
                context['report_filename'])
            response['x-das-download-filename'] = context['report_filename']
        return response

    def get_context_data(self, since, before, event_categories=None, **kwargs):
        return get_daily_report_data(since, before, event_categories=event_categories, **kwargs)


class IsSuperAdminUser(permissions.BasePermission):
    """
    Allows access only to super admin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


def get_tableau_site_id():
    """get the tableau server site id for this ER site. This is used when
    forming the url.

    Returns:
        str: the tableau site id
    """
    try:
        return settings.TABLEAU_SITE_ID if settings.TABLEAU_SITE_ID else get_site_name()
    except AttributeError:
        pass
    return get_site_name()


def get_tableau_api():
    tableau_site_id = get_tableau_site_id()
    trusted_username = f'{tableau_site_id}_tableau_user'
    return TableauAPI(settings.TABLEAU_SERVER, settings.TABLEAU_VERSION,
                      settings.TABLEAU_API_USERNAME, settings.TABLEAU_API_PASSWORD,
                      settings.TABLEAU_API_TOKEN,
                      tableau_site_id, trusted_username)


class TableauAPIError(Exception):
    pass


class TableauAPI:
    def __init__(self, tableau_server, tableau_version, username, password, access_token, site_id, trusted_username):
        self.baseURL = f'{tableau_server}/api/{tableau_version}'
        self.server = tableau_server
        self.site_urlname = site_id
        self.trusted_username = trusted_username
        self.login(username, password, access_token, site_id)

    def login(self, username, password, access_token, site_id):
        """
        POST /api/api-version/auth/signin
        """
        url = f'{self.baseURL}/auth/signin'
        if access_token:
            data = {
                "credentials": {
                    "personalAccessTokenName": username,
                    "personalAccessTokenSecret": access_token,
                }
            }
        else:
            data = {
                "credentials": {
                    "name": username,
                    "password": password,
                }
            }

        data['credentials']['site'] = {'contentUrl': site_id}
        headers = {'content-type': 'application/json',
                   'accept': 'application/json'}
        try:
            response = requests.post(url, json=data, headers=headers)
        except requests.exceptions.ConnectionError as cn:
            logger.exception(
                f"ConnectionFailure: {cn} occured for endpoint: {url}")
        except requests.exceptions.RequestException as exc:
            logger.exception(
                f"Exception raised: {exc} when processing request: {url}")
        else:
            response = json.loads(response.text)

            error = response.get('error')
            credentials = response.get('credentials')
            if error:
                logger.info(f"Authentication failed with error: {error}")
                raise TableauAPIError(error)
            elif credentials:
                self.token = credentials['token']
                self.site_id = credentials['site'].get('id')

    def make_get_request(self, path_component):
        headers = {'content-type': 'application/json',
                   'accept': 'application/json'}
        headers['X-Tableau-Auth'] = f'{self.token}'
        url = f'{self.baseURL}/{path_component}'
        try:
            response = requests.get(url, headers=headers)
        except requests.exceptions.ConnectionError as cn:
            return json.dumps({'error': {'Summary': 'Connection Error', 'detail': f'{cn}'}})
        except requests.exceptions.RequestException as exc:
            return json.dumps({'error': {'Summary': 'RequestException Error', 'detail': f'{exc}'}})
        else:
            return response.text

    def get_views(self):
        """
        Returns all the views for the site.
        GET /api/api-version/sites/site-id/views?pageSize=page-size&pageNumber=page-number
        """
        path = f'sites/{self.site_id}/views?pageSize=1000'
        response = self.make_get_request(path)
        return response

    def get_workbook(self, workbook_id):
        """
        Returns information about the specified workbook, including information about views and tags.
        GET /api/api-version/sites/site-id/workbooks/workbook-id
        """
        path = f'sites/{self.site_id}/workbooks/{workbook_id}'
        response = self.make_get_request(path)
        return response

    def get_view_specific_view(self, view_id):
        """
        Gets the details of a specific view.
        GET /api/api-version/sites/site-id/views/view-id
        """
        path = f'sites/{self.site_id}/views/{view_id}'
        response = self.make_get_request(path)
        return response

    def get_dashboard(self, name):
        views = json.loads(self.get_views())
        for view in views['views']['view']:
            if view["name"] == name:
                return view

    def get_dashboard_by_urlname(self, name):
        views = json.loads(self.get_views())
        for view in views['views']['view']:
            if view["viewUrlName"] == name:
                return view

    def get_site(self):
        """
        Returns information about the site,
        GET /api/api-version/sites/site-id
        """
        path = f'sites/{self.site_id}'
        response = self.make_get_request(path)
        return response

    def get_ticket(self):
        data = {'username': self.trusted_username,
                'target_site': self.site_urlname}
        response = requests.post(url=f'{self.server}/trusted', data=data)
        return response.text


class DashboardSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    display_url = serializers.CharField()
    server = serializers.CharField()


class TableauDashboard(generics.GenericAPIView):
    permission_classes = (IsSuperAdminUser,)
    serializer_class = DashboardSerializer

    def get(self, request, *args, **kwargs):
        dashboard_id = kwargs.get('dashboard_id')
        if dashboard_id == 'default':
            dashboard_id = settings.TABLEAU_DEFAULT_DASHBOARD
        instance = get_tableau_api()

        view = instance.get_dashboard_by_urlname(dashboard_id)
        if not view:
            message = f"Tableau dashboard with viewUrlName={dashboard_id} not found"
            return Response(data=message, status=status.HTTP_400_BAD_REQUEST)

        workbook = json.loads(instance.get_workbook(
            view['workbook']['id']))['workbook']

        ticket = instance.get_ticket()
        if ticket == '-1':
            data = {'ticket': ticket,
                    'status': 'failed to retrieve tableau ticket'}
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        url = f"{instance.server}/trusted/{ticket}/t/{instance.site_urlname}/views/{workbook['contentUrl']}/{view['viewUrlName']}"
        response = {
            'ticket': ticket,
            'display_url': url,
            'server': instance.server}

        return Response(response)


class TableauView(generics.GenericAPIView):
    permission_classes = (IsSuperAdminUser,)

    def get(self, request, *args, **kwargs):
        view_id = kwargs.get('view_id')
        instance = get_tableau_api()

        response = json.loads(instance.get_view_specific_view(view_id))

        view = response.get('view')
        if not view:
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

        workbook_id = view['workbook'].get('id')
        view_urlname = view.get('viewUrlName') if view else None

        response = json.loads(instance.get_workbook(workbook_id))
        if not response.get('workbook'):
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

        site_response = json.loads(instance.get_site())
        if not site_response.get('site'):
            return Response(site_response, status=status.HTTP_400_BAD_REQUEST)

        site_name = site_response['site']['name']
        workbook_contenturl = response['workbook']['contentUrl']

        ticket = instance.get_ticket()
        if ticket == '-1':
            data = {'ticket': ticket,
                    'status': 'failed to retrieve tableau ticket'}
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.TABLEAU_SERVER}/trusted/{ticket}/t/{site_name}/views/{workbook_contenturl}/{view_urlname}'
        response = {'ticket': ticket, 'display_url': url,
                    'server': instance.server}

        return Response(response)


class TableauAPIView(generics.GenericAPIView):
    permission_classes = (IsSuperAdminUser,)

    def get(self, request, *args, **kwargs):
        instance = get_tableau_api()
        views = json.loads(instance.get_views())
        return Response(views)
