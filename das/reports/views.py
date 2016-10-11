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
from reports.reports import get_events, get_conservancies, get_rhino_sightings, get_rhinos, get_security_event
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

def extract_details(details):

    for k, v in details.items():
        if isinstance(v, dict) and 'name' in v:
            yield {'name': k, 'value': escape(v['name'])}
        elif isinstance(v, (int, float, bool)):
            yield {'name': k, 'value': str(v)}
        elif isinstance(v, str):
            yield {'name': k, 'value': escape(v)}


EVENT_LIST_TIMESTAMP_FORMAT = '%-d-%b %H:%M'
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
            response['Content-Disposition'] = 'attachment; filename={}'.format(context['report_filename'])
            response['x-das-download-filename'] = context['report_filename']
        return response

    def get_context_data(self, since, before, **kwargs):
        '''
        This applies brute-force the the events, marching through the various sections of a Sit Rep and filling in the
        blanks.
        :param kwargs:
        :return:
        '''
        report_time = timezone.now()

        # Get the events we're interested in. We just need this list once and we'll run it through a set of
        # accumulotors that take whatever they need to hydrate the sit-rep report.
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
            (k.lower(), {'conservancy':k,
                         'total_rhino_black': b,
                         'total_rhino_white': w,
                         'denominator': {
                             'black_rhino_sighting': b,
                             'white_rhino_sighting': w,
                         'total': b+w}}) for (k,b,w) in conservancy_census)

        # Convenience method to initialize a 'wildlife_sightings' block for a single conservancy.
        def default_conservancy_ws(conservancy):
            c = {'total_sightings': 0,
                 'rhino_sightings': [
                     {'type': 'Black Rhino',
                      'event_type': 'black_rhino_sighting',
                      'count': 0,
                      'percentage': 0},
                     {'type': 'White Rhino',
                      'event_type': 'white_rhino_sighting',
                      'count': 0,
                      'percentage': 0}
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
            denominator = conservancy['denominator'].get('total')

            conservancy['percentage'] = '%d%%' % (100 * conservancy['total_sightings'] / denominator, ) if denominator else '-%'
            for item in conservancy['rhino_sightings']:

                if item['event_type'] == event.event_type.value:
                    item['count'] += 1
                    denominator = conservancy['denominator'].get(event.event_type.value)
                    item['percentage'] = '%d%%' % (100 * item['count'] / denominator,) if denominator else '-%'
        rhino_sightings = accumulator({}, rhino_sightings)

        # Accumulator for 'Rhino Births'
        def rhino_births(accum, event):
            if event.event_type.value != 'rhino_birth':
                return

            conservancy = get_conservancy(event)
            ed = event.event_details.first()
            if not ed or not ed.data or not 'event_details' in ed.data:
                return
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
            if not ed or not ed.data or 'event_details' not in ed.data:
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
            if not ed or not ed.data or 'event_details' not in ed.data:
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
            if not ed or not ed.data or 'event_details' not in ed.data:
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
            if not ed or not ed.data or 'event_details' not in ed.data:
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
            if not ed or not ed.data or 'event_details' not in ed.data:
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

        # Accumulator for 'fence breakage'
        def fence_breakage(accum, event):
            if event.event_type.value != 'fence_breakage':
                return
            ed = event.event_details.first()
            if not ed or not ed.data or 'event_details' not in ed.data:
                return
            ed = ed.data['event_details']

            etime = event.event_time.astimezone(timezone.get_current_timezone())
            b = {'time': etime.strftime(EVENT_LIST_TIMESTAMP_FORMAT),
                 'section': safe_get(ed, ('fenceSection', 'name'), 'unspecified'),
                 'species': safe_get(ed, ('species', 'name'), 'unspecified'),
                 'animal_name': escape(ed.get('animal_name', '')),
                 'reported_by': escape(ed.get('reported_by', '')),
                 'action': safe_get(ed, ('actionTaken', 'name'), 'unspecified'),
                'feedback': escape(ed.get('feedback', ''))
                 }

            accum.append(b)

        fence_breakage = accumulator([], fence_breakage)

        # Accumulator for 'security events'
        def security_events(accum, event):
            if event.event_type.category.value != 'security':
                return

            # Special case: exclude human_wildlife_conflict events which are to be included in another section of
            #               this report.
            if event.event_type.value == 'human_wildlife_conflict':
                return

            ed = event.event_details.first()
            if not ed or not ed.data or 'event_details' not in ed.data:
                return
            ed = ed.data['event_details']

            accum.append({'message': escape(event.message),
                    'event_name': escape(event.event_type.display),
                    'event_time': event.event_time.astimezone(timezone.get_current_timezone()).strftime(EVENT_LIST_TIMESTAMP_FORMAT),
                    'attributes': extract_details(ed)
                    })

        security_events = accumulator([], security_events)

        # Accumulator for 'human wildlife conflict'
        def human_wildlife_conflict(accum, event):
            if event.event_type.value != 'human_wildlife_conflict':
                return
            ed = event.event_details.first()
            if not ed or not ed.data or 'event_details' not in ed.data:
                return
            ed = ed.data['event_details']
            accum.append({'message': escape(event.message),
                    'event_name': escape(event.event_type.display),
                    'event_time': event.event_time.astimezone(timezone.get_current_timezone()).strftime(EVENT_LIST_TIMESTAMP_FORMAT),
                    'attributes': extract_details(ed)
                    })


        human_wildlife_conflict = accumulator([], human_wildlife_conflict)
        b = broadcast((rhino_sightings, rhino_births, rhino_territorial_movement, other_wildlife_sightings, carcass,
                       gap_movement, rainfall, fence_breakage, security_events, human_wildlife_conflict))

        for event in events:
            b.send(event)

        rhino_births = rhino_births.send(None)
        rhino_territorial_movement = rhino_territorial_movement.send(None)
        other_wildlife_sightings = other_wildlife_sightings.send(None)
        carcass = carcass.send(None)
        gap_movement = gap_movement.send(None)
        rainfall = rainfall.send(None)
        fence_breakage = fence_breakage.send(None)
        wildlife_sightings_per_conservancy = rhino_sightings.send(None)
        security_events = security_events.send(None)
        human_wildlife_conflict = human_wildlife_conflict.send(None)

        #
        # Query for rhino sightings over the last 7 days, to determine which rhinos are 'missing' for
        # an inordinate time.
        #
        near_threshold = before - datetime.timedelta(days=3)
        far_threshold = before - datetime.timedelta(days=7)
        rhino_sighting_events = get_rhino_sightings(far_threshold, before)
        missing_rhinos = dict((str(r.id), {'name': escape(r.name), 'days_ago': 1000000}) for r in get_rhinos())

        for event in rhino_sighting_events:
            ed = event.event_details.first()
            if not ed or not ed.data or 'event_details' not in ed.data:
                continue
            ed = ed.data['event_details']
            rhino_id = ed['blackRhinos']['value'] if 'blackRhinos' in ed else ed['whiteRhinos']['value'] if 'whiteRhinos' in ed else None
            if rhino_id:
                if event.event_time > near_threshold:
                     missing_rhinos.pop(rhino_id, None)
                else:
                    missing_rhinos[rhino_id]['days_ago'] = min(missing_rhinos[rhino_id]['days_ago'],
                                                               (before - event.event_time).days)

        # Post-process missing rhinos.
        for r in missing_rhinos.values():
            r['days_ago'] = '> 7' if r['days_ago'] > 7 else str(r['days_ago'])

        missing_rhinos = list(missing_rhinos.values())

        REPORT_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S %Z'
        since_text = since.astimezone(timezone.get_current_timezone()).strftime(REPORT_TIMESTAMP_FORMAT)
        before_text = before.astimezone(timezone.get_current_timezone()).strftime(REPORT_TIMESTAMP_FORMAT)
        context = {
            'report_filename': 'Daily-SitRep-{}.docx'.format(report_time.strftime('%Y-%m-%d')),
            'report_time': report_time.astimezone(timezone.get_current_timezone()).strftime('%-d %B %Y %Z'),
            'report_daterange_text': 'Including events from: {} to: {}'.format(since_text, before_text),
            'footer_text': 'Report generated by DAS user {username} at {report_time}'.format(
                report_time=report_time.strftime(REPORT_TIMESTAMP_FORMAT),
                username=self.request.user.get_username()),

            'wildlife_sightings': wildlife_sightings_per_conservancy.values(),

            'rhino_births': rhino_births,

            'missing_rhinos': missing_rhinos,

            'rhino_territorial_movement': rhino_territorial_movement,

            'other_sightings': other_wildlife_sightings.values(),

            'carcass': carcass,

            'gap_movement': gap_movement,

            'rainfall': rainfall.values(),

            'fence_breakage': fence_breakage,

            'security_events': security_events,

            'human_wildlife_conflict': human_wildlife_conflict,

        }

        return context

