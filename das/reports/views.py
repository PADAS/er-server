import pytz, datetime
from collections import Counter

from django.utils import timezone
from django.shortcuts import render
from django.views.generic import TemplateView
from django.template.response import TemplateResponse
from rest_framework import status
from rest_framework.response import Response

from rest_framework import serializers, views, permissions
from django.views.generic.base import TemplateResponseMixin, ContextMixin
from reports.reports import get_events, get_conservancies


class ReportDateParameters(serializers.Serializer):
    since = serializers.DateTimeField(default=None)
    before = serializers.DateTimeField(default=None)


class ReportView(views.APIView):
    def dispatch(self, request, report_key, *args, **kwargs):
        print(args, kwargs)
        if report_key == 'sitrep':
            return SituationReportView().dispatch(request, *args, **kwargs)


def coroutine(f):
    def wrapper(*args, **kwargs):
        c = f(*args, **kwargs)
        c.send(None)
        return c
    return wrapper

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
        since = qs.get('since') or  (now - datetime.timedelta(hours=24))
        before = qs.get('before') or now


        context = self.get_context_data(since=since, before=before, **kwargs)
        return self.render_to_response(context)

    def render_to_response(self, context, **response_kwargs):

        response = super().render_to_response(context, **response_kwargs)
        response['Content-Disposition'] = 'attachement; filename={}'.format(context['report_filename'])
        return response

    def get_context_data(self, since, before, **kwargs):
        '''
        This applies brute-force the the events, marching through the various sections of a Sit Rep and filling in the
        blanks.
        :param kwargs:
        :return:
        '''
        # conservancies = get_conservancies()
        report_time = timezone.now()

        events = get_events(since, before)

        CONSERVANCY_UNSPECIFIED = '&lt;unspecified&gt;'
        def get_conservancy(event):
            ed = event.event_details.all().order_by('-created_at').first()
            if ed:
                try:
                    return ed.data['event_details']['conservancy']['name']
                except Exception as e:
                    print(e)
                    pass
            return CONSERVANCY_UNSPECIFIED

        @coroutine
        def total_rhino_black():
            value = 0
            while True:
                try:
                    event = yield value
                    if event and event.event_type.value == 'black_rhino_sighting':
                        value += 1
                except Exception as e:
                    print(e)

        f = total_rhino_black()
        val = 0
        for event in events:
            val = f.send(event)

        print('Val: %s' % (f.send(None),))

        #
        # Populate wildlife_sightings for the first portion of the report.
        #
        # TODO: The schema changed for rhino sightings, to include a list of rhinos. So update here to reflect this.
        conservancy_census = [('Lewa', 62, 66), ('Borana', 21, 0), ('Sera', 10, 0), (CONSERVANCY_UNSPECIFIED, 0, 0)]
        conservancy_census = dict(
            (k.lower(), {'conservancy':k, 'total_rhino_black': b, 'total_rhino_white': w}) for (k,b,w) in conservancy_census)

        def default_conservancy_ws(conservancy):
            c = {'total_sightings': 0,
                 'rhino_sightings': [
                     {'type': 'Black Rhino',
                      'event_type': 'black_rhino_sighting',
                      'count': 0},
                     {'type': 'White Rhino',
                      'event_type': 'white_rhino_sighting',
                      'count': 0}
                 ]}
            c.update(conservancy_census.get(conservancy.lower(), {}))
            return c

        wildlife_sightings_per_conservancy = {}
        for event in events:
            if 'rhino_sighting' not in event.event_type.value:
                continue

            conservancy = get_conservancy(event)
            conservancy = wildlife_sightings_per_conservancy.setdefault(conservancy, default_conservancy_ws(conservancy))

            conservancy['total_sightings'] += 1
            for item in conservancy['rhino_sightings']:
                if item['event_type'] == event.event_type.value:
                    item['count'] += 1

        #
        # Populuate rhino births.
        #




        context = {
            'report_filename': 'sitrep_report-{}.docx'.format(report_time.strftime('%Y-%m-%d')),
            'report_time': report_time.astimezone(pytz.timezone('Africa/Nairobi')).strftime(
                '%-d %B %Y %Z'),
            'report_daterange_text': 'Including events from: {} to: {}'.format(since.isoformat(), before.isoformat()),
            'footer_text': 'Report generated by DAS user {username} at {report_time}'.format(report_time=report_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                                                                                         username=self.request.user.get_username()),

            'wildlife_sightings': wildlife_sightings_per_conservancy.values(),


            'rhino_births': [],

            'rhino_missing': [
                {'name': 'Folly', 'value': 4},
                {'name': 'Elvis', 'value': 3},
                {'name': 'Muturi', 'value': 4},
                {'name': 'Seneiya + calf 1', 'value': 3},
            ],

            'rhino_territorial_movement': [

            ],

            'other_sightings': [
                {'conservancy': 'Lewa',
                 'total_sightings': 125,
                 'sightings': [
                     {'species': 'elephant', 'count': 50},
                     {'species': 'buffalo', 'count': 75},
                 ]
                 },
                {'conservancy': 'Borana',
                 'total_sightings': 170,
                 'sightings': [
                     {'species': 'elephant', 'count': 118},
                     {'species': 'buffalo', 'count': 52},
                 ]
                 },

            ],

            'gap_counts': [
                {'gap_name': 'Leparua 2 Gap', 'species': 'elephant', 'total_in': 4, 'total_out': 0},
            ],

            'rainfall': [
                {'conservancy_name': 'Lewa'},
                {'conservancy_name': 'Borana'},
                {'conservancy_name': 'Sera'},
            ],

        }

        return context

