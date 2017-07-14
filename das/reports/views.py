import pytz
import datetime
from collections import Counter

from django.utils import timezone
from django.template.response import TemplateResponse
from rest_framework import status
from rest_framework.response import Response

from rest_framework import serializers, views, permissions
from django.views.generic.base import TemplateResponseMixin, ContextMixin

from reports.reports import get_daily_report_data


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
