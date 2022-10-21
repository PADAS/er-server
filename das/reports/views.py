import datetime
import json
import logging

import requests

from django.conf import settings
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.generic.base import ContextMixin, TemplateResponseMixin
from rest_framework import generics, permissions, serializers, status, views
from rest_framework.response import Response

from activity.models import EventCategory
from activity.permissions import EventCategoryPermissions
from core.utils import get_site_name
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
        except requests.exceptions.ConnectionError as ce:
            message = f"ConnectionFailure: {ce} occured for endpoint: {url}"
            raise TableauAPIError(message) from ce
        except requests.exceptions.RequestException as exc:
            message = f"Exception raised: {exc} when processing request: {url}"
            raise TableauAPIError(message) from exc
        else:
            response = json.loads(response.text)

            error = response.get('error')
            if error:
                raise TableauAPIError(
                    f"Authentication failed with error: {error}")

            credentials = response.get('credentials')
            if not credentials:
                raise TableauAPIError("No credentials found in signin request")
            self.token = credentials['token']
            self.site_id = credentials['site'].get('id')

    def make_get_request(self, path_component):
        headers = {'content-type': 'application/json',
                   'accept': 'application/json'}
        headers['X-Tableau-Auth'] = f'{self.token}'
        url = f'{self.baseURL}/{path_component}'
        try:
            response = requests.get(url, headers=headers)
        except requests.exceptions.ConnectionError as ce:
            message = f"ConnectionFailure: {ce} occured for endpoint: {url}"
            raise TableauAPIError(message) from ce
        except requests.exceptions.RequestException as exc:
            message = f"Exception raised: {exc} when processing request: {url}"
            raise TableauAPIError(message) from exc
        response = json.loads(response.text)
        error = response.get('error')
        if error:
            raise TableauAPIError(
                f"Tableau API request failed with error: {error}")
        return response

    def get_views(self):
        """
        Returns all the views for the site.
        GET /api/api-version/sites/site-id/views?pageSize=page-size&pageNumber=page-number
        """
        path = f'sites/{self.site_id}/views?pageSize=1000'
        for view in self.make_get_request(path)['views']['view']:
            yield view

    def get_workbooks(self):
        """
        Returns all the workbooks for the site.
        GET /api/api-version/sites/site-id/workbooks?pageSize=page-size&pageNumber=page-number
        """
        path = f'sites/{self.site_id}/workbooks?pageSize=1000'
        for workbook in self.make_get_request(path)["workbooks"]["workbook"]:
            yield workbook

    def get_workbook_by(self, field, value):
        for wb in self.get_workbooks():
            if wb[field] == value:
                return wb

    def get_workbook(self, workbook_id):
        """
        Returns information about the specified workbook, including information about views and tags.
        GET /api/api-version/sites/site-id/workbooks/workbook-id
        """
        path = f'sites/{self.site_id}/workbooks/{workbook_id}'
        return self.make_get_request(path)["workbook"]

    def get_view(self, view_id):
        """
        Gets the details of a specific view.
        GET /api/api-version/sites/site-id/views/view-id
        """
        path = f'sites/{self.site_id}/views/{view_id}'
        return self.make_get_request(path)["view"]

    def get_dashboard(self, name, workbook=None):
        """Get the dashboard, which is really a view. Optionally include the workbook name if there are more than one view with the same name in a site

        Args:
            name (str): view name
            workbook (str, optional): workbook name. Defaults to None.

        Returns:
            _type_: _description_
        """
        if workbook:
            workbook = self.get_workbook_by("name", workbook)

        for view in self.get_views():
            if workbook and workbook["id"] != view["workbook"]["id"]:
                continue

            if view["name"] == name:
                return view

    def get_dashboard_by_urlname(self, name, workbook=None):
        """Get the dashboard view using the view id as encoded in a Tableau Url referencing the view.

        Args:
            name (str): the view id
            workbook (_type_, optional): workbook name, additionaly match on workbook name as it's possible to use the same view name in multiple workbooks. Defaults to None.

        Returns:
            _type_: _description_
        """
        if workbook:
            workbook = self.get_workbook_by("contentUrl", workbook)

        for view in self.get_views():
            if workbook and view["workbook"]["id"] != workbook["id"]:
                continue
            if view["viewUrlName"] == name:
                return view

    def get_site(self):
        """
        Returns information about the site,
        GET /api/api-version/sites/site-id
        """
        path = f'sites/{self.site_id}'
        return self.make_get_request(path)

    def get_ticket(self):
        data = {'username': self.trusted_username,
                'target_site': self.site_urlname}
        response = requests.post(url=f'{self.server}/trusted', data=data)
        return response.text


class DashboardSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    display_url = serializers.CharField()
    server = serializers.CharField()


class TableauViewTicketGenerator:
    def get_ticket_for_dashboard(self, dashboard_id):
        workbook_id, view_id = self.split_view(dashboard_id)

        try:
            instance = get_tableau_api()
            view = instance.get_dashboard_by_urlname(view_id, workbook_id)
            if not view:
                message = f"Tableau dashboard with viewUrlName={view_id} in workbook={workbook_id} not found"
                return Response(data=message, status=status.HTTP_400_BAD_REQUEST)

            return self._get_ticket_for_view(instance, view)
        except TableauAPIError as t_api:
            message = f"Tableau dashboard with viewUrlName={view_id} in workbook={workbook_id} not found, error {t_api}"
            return Response(data=message, status=status.HTTP_400_BAD_REQUEST)

    def get_ticket_for_view(self, view_id):
        try:
            instance = get_tableau_api()
            view = instance.get_view(view_id)
            if not view:
                message = f"Tableau dashboard with viewUrlName={view_id}not found"
                return Response(data=message, status=status.HTTP_400_BAD_REQUEST)

            return self._get_ticket_for_view(instance, view)
        except TableauAPIError as t_api:
            message = f"Tableau dashboard with view_id={view_id} not found, error {t_api}"
            return Response(data=message, status=status.HTTP_400_BAD_REQUEST)

    def _get_ticket_for_view(self, instance, view):

        workbook = instance.get_workbook(view['workbook']['id'])

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

    def split_view(self, view_id):
        """Support splitting the encoding of the workbook and view ids together in one string.

        Args:
            view_id (_type_): view_id, optionally including workbook_id as "workbook_id/view_id"

        Returns:
            tuple: workbook_id, view_id
        """
        if "/" in view_id:
            return view_id.split("/")
        return None, view_id


class TableauDashboard(generics.GenericAPIView, TableauViewTicketGenerator):
    permission_classes = (IsSuperAdminUser,)
    serializer_class = DashboardSerializer

    def get(self, request, *args, **kwargs):
        dashboard_id = kwargs.get('dashboard_id')
        if dashboard_id == 'default':
            dashboard_id = settings.TABLEAU_DEFAULT_DASHBOARD
        return self.get_ticket_for_dashboard(dashboard_id)


class TableauView(generics.GenericAPIView, TableauViewTicketGenerator):
    permission_classes = (IsSuperAdminUser,)

    def get(self, request, *args, **kwargs):
        view_id = kwargs.get('view_id')

        return self.get_ticket_for_view(view_id)


class TableauAPIView(generics.GenericAPIView):
    permission_classes = (IsSuperAdminUser,)

    def get(self, request, *args, **kwargs):
        instance = get_tableau_api()
        return Response(list(instance.get_views()))
