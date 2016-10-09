import pytz, datetime
from collections import Counter

from django.utils import timezone
from django.utils.html import escape
from django.shortcuts import render
from django.views.generic import TemplateView
from django.template.response import TemplateResponse
from rest_framework import status
from rest_framework.response import Response

from rest_framework import serializers, views, permissions
from django.views.generic.base import TemplateResponseMixin, ContextMixin
from reports.reports import get_events, get_conservancies
from reports.accumulator import accumulator, broadcast

class ReportDateParameters(serializers.Serializer):
    since = serializers.DateTimeField(default=None)
    before = serializers.DateTimeField(default=None)


class ReportView(views.APIView):
    def dispatch(self, request, report_key, *args, **kwargs):
        print(args, kwargs)
        if report_key == 'sitrep':
            return SituationReportView().dispatch(request, *args, **kwargs)



def safe_get(val, keys, default=None):

    try:
        for k in keys:
            val = val[k]
        if isinstance(val, str):
            return escape(val)
    except KeyError:
        pass
    return default

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
        if 'openxmlformats' in self.content_type:
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


        conservancy_census = [('Lewa', 62, 66), ('Borana', 21, 0), ('Sera', 10, 0), (CONSERVANCY_UNSPECIFIED, 0, 0)]
        conservancy_census = dict(
            (k.lower(), {'conservancy':k, 'total_rhino_black': b, 'total_rhino_white': w}) for (k,b,w) in conservancy_census)

        # Convenience method to initialize a 'wildlife_sightings' block for a single conservancy.
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


        # Accumulator for the 'Wildlife Sightings' portion of report.
        def rhino_sightings(accum, event):

            if 'rhino_sighting' not in event.event_type.value:
                return

            conservancy = get_conservancy(event)
            conservancy = accum.setdefault(conservancy, default_conservancy_ws(conservancy))

            conservancy['total_sightings'] += 1
            for item in conservancy['rhino_sightings']:
                if item['event_type'] == event.event_type.value:
                    item['count'] += 1
        rhino_sightings = accumulator({}, rhino_sightings)

        # Accumulator for 'Rhino Births'
        def rhino_births(accum, event):
            if event.event_type.value != 'rhino_birth':
                return

            conservancy = get_conservancy(event)
            ed = event.event_details.first()
            ed = ed.data['event_details']
            new_birth = {'conservancy': conservancy,
                         'color': safe_get(ed, ('color', 'name'), 'unspecified'),
                         'mother': safe_get(ed, ('femaleRhinos', 'name'), 'unspecified'),
                         'health': safe_get(ed, ('health', 'name'), 'unspecified'),
                         }
            accum.append(new_birth)
        rhino_births = accumulator([], rhino_births)

        # Accumulaotor for 'Rhino territorial movement'
        def rhino_territorial_movement(accum, event):
            if event.event_type.value != 'rhino_territorial_movement':
                return

            conservancy = get_conservancy(event)
            ed = event.event_details.first()
            if not ed:
                return
            ed = ed.data['event_details']

            accum.append(
                {'conservancy': conservancy,
                  'color': safe_get(ed, ('color', 'name'), 'unspecified'),
                  'rhinos': safe_get(ed, ('rhinos', 'name'), 'unspecified'),
                  'health': safe_get(ed, ('health', 'name'), 'unspecified'),
                  'station': safe_get(ed, ('station', 'name'), 'unspecified'),
                  'behavior': safe_get(ed, ('behavior', 'name'), 'unspecified'),
                })

        rhino_territorial_movement = accumulator([], rhino_territorial_movement)

        # Accumulator for 'other wildlife sightings' per Conservancy
        def other_wildlife_sightings(accum, event):
            if event.event_type.value != 'other_wildlife_sightings':
                return

            conservancy = get_conservancy(event)
            conservancy = accum.setdefault(conservancy.lower(), {'conservancy': conservancy,
                                                                 'total_sightings': 0,
                                                                 'sightings': [] })

            ed = event.event_details.first()
            if not ed:
                return
            ed = ed.data['event_details']

            species = safe_get(ed, ('species', 'name'), None)
            if not species:
                return

            conservancy['total_sightings'] += ed.get('numberAnimals', 0)

            for s in conservancy['sightings']:
                if s['species'] == species:
                    s['count'] += 1
                    break
            else:
                conservancy['sightings'].append({'species':species, 'count': ed.get('numberAnimals', 0)})

        other_wildlife_sightings = accumulator({}, other_wildlife_sightings)

        def carcass(accum, event):
            if event.event_type.value != 'loss_of_animal_life':
                return
            ed = event.event_details.first()
            if not ed:
                return
            ed = ed.data['event_details']

            accum.append(
                {'conservancy': safe_get(ed, ('conservancy', 'name'), 'unspecified'),
                 'species': safe_get(ed, ('species', 'name'), 'unspecified'),
                 'cause_of_death': safe_get(ed, ('causeOfDeath', 'name'), 'unspecified'),
                 'station': safe_get(ed, ('station', 'name'), 'unspecified'),
                 'number_animals': ed.get('number_animals', 0),
                 })

        carcass = accumulator([], carcass)

        # Accumulator for 'movement through gaps'
        def gap_movement(accum, event):
            if event.event_type.value != 'wildlife_gap_movement':
                return

            ed = event.event_details.first()
            if not ed:
                return
            ed = ed.data['event_details']

            gap = safe_get(ed, ('wildlifeGap', 'name'), None)
            species = safe_get(ed, ('species', 'name'), 'unspecified')
            if not gap: return

            for sum in accum:
                if sum['gap_name'] == gap and sum['species']  == species:
                    sum['total_in'] += ed['number_in']
                    sum['total_out'] += ed['number_out']
                    break
            else:
                accum.append({'gap_name': gap,
                              'species': species,
                              'total_in': ed['number_in'],
                              'total_out': ed['number_out']})

        gap_movement = accumulator([], gap_movement)


        # TODO: Accumulate human wildlife conflict (security events)

        # Accumulator for 'Rainfall'
        def rainfall(accum, event):
            if event.event_type.value != 'rainfall_report':
                return
            ed = event.event_details.first()
            if not ed:
                return
            ed = ed.data['event_details']

            conservancy = safe_get(ed, ('conservancy', 'name'), 'unspecified')
            station = safe_get(ed, ('station', 'name'), 'unspecified')
            mm = ed.get('number_rainfall', 0)

            c = accum.setdefault(conservancy, {'conservancy': conservancy,
                                               'rainfall': []})

            for sum in c['rainfall']:
                if sum['station'] == station:
                    sum['total_mm'] += mm
                    break
            else:
                c['rainfall'].append({'station': station, 'total_mm': mm})

        rainfall = accumulator({}, rainfall)


        b = broadcast((rhino_sightings, rhino_births, rhino_territorial_movement, other_wildlife_sightings, carcass,
                       gap_movement, rainfall))
        for event in events:
            b.send(event)

        rhino_births = rhino_births.send(None)
        rhino_territorial_movement = rhino_territorial_movement.send(None)
        other_wildlife_sightings = other_wildlife_sightings.send(None)
        carcass = carcass.send(None)
        gap_movement = gap_movement.send(None)
        rainfall = rainfall.send(None)

        #
        # Populate wildlife_sightings for the first portion of the report.
        #
        # TODO: The schema changed for rhino sightings, to include a list of rhinos. So update here to reflect this.
        wildlife_sightings_per_conservancy = rhino_sightings.send(None)

        context = {
            'report_filename': 'sitrep_report-{}.docx'.format(report_time.strftime('%Y-%m-%d')),
            'report_time': report_time.astimezone(pytz.timezone('Africa/Nairobi')).strftime(
                '%-d %B %Y %Z'),
            'report_daterange_text': 'Including events from: {} to: {}'.format(since.isoformat(), before.isoformat()),
            'footer_text': 'Report generated by DAS user {username} at {report_time}'.format(report_time=report_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                                                                                         username=self.request.user.get_username()),

            'wildlife_sightings': wildlife_sightings_per_conservancy.values(),


            'rhino_births': rhino_births,

            'rhino_missing': [
                {'name': 'Folly', 'value': 4},
                {'name': 'Elvis', 'value': 3},
                {'name': 'Muturi', 'value': 4},
                {'name': 'Seneiya + calf 1', 'value': 3},
            ],

            'rhino_territorial_movement': rhino_territorial_movement,

            'other_sightings': other_wildlife_sightings.values(),

            'carcass': carcass,

            'gap_movement': gap_movement,

            'rainfall': rainfall.values(),

        }

        return context

