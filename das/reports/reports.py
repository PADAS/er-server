import platform
from datetime import datetime, timedelta

import html
from django.utils import timezone
from django.db.models import *

from activity.models import Event
from choices.models import Choice
from observations.models import Subject

from django.utils.html import escape

from reports.accumulator import accumulator, broadcast

import utils.schema_utils as schema_utils
from utils.memoize import memoize


HWC_REPORT_TYPES = ('human_wildlife_conflict', 'hwc_crp',
                    'hwc_human', 'hwc_prd', 'hwc_pd', 'hwc_retaliation')


@memoize
def get_choices(field):
    return {c.value: c.display for c in Choice.objects.get_choices(model=Choice.Field_Reports,
                                                                   field=field)}


@memoize
def get_dynamic_choices(field):
    field_details = dict(field=field, type='names')
    choices = schema_utils._get_dynamic_choices(field_details)
    return choices


def safe_get_choice(val, key, choice_field, default=None, is_dynamic=False):
    if is_dynamic:
        choices = get_dynamic_choices(choice_field)
    else:
        choices = get_choices(choice_field)

    try:
        val = val[key]
        if isinstance(val, dict):
            # With the old choice tables, we stored a dict of "name", "value"
            # pairs
            val = val['value']
        if isinstance(val, str):
            return escape(choices[val])
    except (KeyError, TypeError):
        pass
    return default


def _listify(o):

    if o is None:
        return []
    if isinstance(o, (dict, str)):
        return [o, ]
    if isinstance(o, list):
        return o
    return []


EVENT_LIST_TIMESTAMP_FORMAT = '%-d-%b %H:%M' if platform.system().lower() != 'windows' else '%#d-%b %H:%M'


def get_permitted_events(start=None, end=None, event_categories=None):

    if not event_categories:
        return Event.objects.none()

    queryset = Event.objects.filter(event_type__category__in=event_categories) \
        .filter(event_time__range=[start, end])
    return queryset


def get_events(start=None, end=None, event_categories=None):
    events = get_permitted_events(start=start, end=end, event_categories=event_categories) \
        .prefetch_related('event_type', 'reported_by') \
        .order_by('event_time')
    return events


def get_conservancies():
    return get_choices('conservancy')


def get_rhino_sightings(start=None, end=None, event_categories=None):
    events = get_permitted_events(start=start, end=end, event_categories=event_categories) \
        .filter(event_type__value__in=('black_rhino_sighting', 'white_rhino_sighting'),
                event_time__range=[start, end])
    return events


def get_rhinos():
    rhinos = Subject.objects.filter(subject_subtype='rhino')
    return rhinos


def get_security_event(start=None, end=None, event_categories=None):
    security_events = get_permitted_events(start=start, end=end, event_categories=event_categories) \
        .filter(event_time__range=[start, end], event_type__category__value='security')
    security_events = security_events.prefetch_related(
        'event_type', 'reported_by').order_by('-event_time')
    return security_events


def get_daily_report_data(since, before, event_categories=None, **kwargs):
    '''
    This applies brute-force the the events, marching through the various sections of a Sit Rep and filling in the
    blanks.
    :param kwargs:
    :return:
    '''
    generated_at = timezone.now()

    render_schema = schema_utils.get_schema_renderer_method()

    # Get the events we're interested in. We just need this list once and we'll run it through a set of
    # accumulotors that take whatever they need to hydrate the sit-rep
    # report.
    events = get_events(start=since, end=before,
                        event_categories=event_categories)

    CONSERVANCY_UNSPECIFIED = '&lt;unspecified&gt;'

    def get_conservancy(event):
        ed = event.event_details.all().order_by('-created_at').first()
        if ed:
            try:
                return safe_get_choice(ed.data['event_details'], 'conservancy', 'conservancy', CONSERVANCY_UNSPECIFIED)
            except Exception as e:
                pass
        return CONSERVANCY_UNSPECIFIED

    conservancy_census = [('--Lewa--', 62, 66), ('Lewa', 62, 66), ('Borana', 21, 0),
                          ('Sera', 10, 0), (CONSERVANCY_UNSPECIFIED, 0, 0)]
    conservancy_census = dict(
        (k.lower(), {'conservancy': k,
                     'total_rhino_black': b,
                     'total_rhino_white': w,
                     'denominator': {
                         'black_rhino_sighting': b,
                         'white_rhino_sighting': w,
                         'total': b + w}}) for (k, b, w) in conservancy_census)

    # Convenience method to initialize a 'wildlife_sightings' block for a
    # single conservancy.
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
        census = conservancy_census.get(
            conservancy.lower()) or conservancy_census.get(CONSERVANCY_UNSPECIFIED)
        c.update(census)
        return c

    # Accumulator for the 'Wildlife Sightings' portion of report.
    def rhino_sightings(accum, event):

        if 'rhino_sighting' not in event.event_type.value:
            return

        conservancy = get_conservancy(event)
        conservancy = accum.setdefault(
            conservancy, default_conservancy_ws(conservancy))

        conservancy['total_sightings'] += 1
        denominator = conservancy['denominator'].get('total')

        conservancy['percentage'] = '%d%%' % (
            100 * conservancy['total_sightings'] / denominator, ) if denominator else '-%'
        for item in conservancy['rhino_sightings']:

            if item['event_type'] == event.event_type.value:
                item['count'] += 1
                denominator = conservancy['denominator'].get(
                    event.event_type.value)
                item['percentage'] = '%d%%' % (
                    100 * item['count'] / denominator,) if denominator else '-%'
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
                     'color': safe_get_choice(ed, 'color', 'color', 'unspecified'),
                     'mother': safe_get_choice(ed, 'femaleRhinos', 'femaleRhinos', 'unspecified', is_dynamic=True),
                     'health': safe_get_choice(ed, 'health', 'health', 'unspecified'),
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

        rhino_names = ', '.join([safe_get_choice(dict(rhino=_), 'rhino', 'rhinos', 'unspecified', is_dynamic=True)
                                 for _ in _listify(ed.get('rhino'))])
        accum.append(
            {'conservancy': conservancy,
             'color': safe_get_choice(ed, 'color', 'color', 'unspecified'),
             'rhinos': escape(rhino_names),
             'health': safe_get_choice(ed, 'health', 'health', 'unspecified'),
             'station': safe_get_choice(ed, 'station', 'station', 'unspecified'),
             'behavior': safe_get_choice(ed, 'behavior', 'behavior', 'unspecified'),
             })

    rhino_territorial_movement = accumulator(
        [], rhino_territorial_movement)

    # Accumulator for 'other wildlife sightings' per Conservancy
    def other_wildlife_sightings(accum, event):
        if event.event_type.value != 'other_wildlife_sightings':
            return

        conservancy = get_conservancy(event)
        conservancy = accum.setdefault(conservancy.lower(), {'conservancy': conservancy,
                                                             'total_sightings': 0,
                                                             'sightings': []})

        ed = event.event_details.first()
        if not ed or not ed.data or 'event_details' not in ed.data:
            return
        ed = ed.data['event_details']

        species = safe_get_choice(ed, 'species', 'species', None)
        if not species:
            return

        conservancy['total_sightings'] += ed.get('numberAnimals', 0)

        for s in conservancy['sightings']:
            if s['species'] == species:
                s['count'] += 1
                break
        else:
            conservancy['sightings'].append(
                {'species': species, 'count': ed.get('numberAnimals', 0)})

    other_wildlife_sightings = accumulator({}, other_wildlife_sightings)

    def carcass(accum, event):
        if event.event_type.value != 'loss_of_animal_life':
            return
        ed = event.event_details.first()
        if not ed or not ed.data or 'event_details' not in ed.data:
            return
        ed = ed.data['event_details']

        accum.append(
            {'conservancy': safe_get_choice(ed, 'conservancy', 'conservancy', 'unspecified'),
             'species': safe_get_choice(ed, 'species', 'species', 'unspecified'),
             'cause_of_death': safe_get_choice(ed, 'causeOfDeath', 'causeofdeath', 'unspecified'),
             'section_area': safe_get_choice(ed, 'sectionarea', 'sectionarea', 'unspecified'),
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

        gap = safe_get_choice(ed, 'wildlifeGap', 'wildlifegap', None)
        species = safe_get_choice(ed, 'species', 'species', 'unspecified')
        if not gap:
            return

        for sum in accum:
            if sum['gap_name'] == gap and sum['species'] == species:
                sum['total_in'] += ed.get('number_in', 0)
                sum['total_out'] += ed.get('number_out', 0)
                break
        else:
            accum.append({'gap_name': gap,
                          'species': species,
                          'total_in': ed.get('number_in', 0),
                          'total_out': ed.get('number_out', 0)})

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

        conservancy = safe_get_choice(
            ed, 'conservancy', 'conservancy', 'unspecified')
        station = safe_get_choice(ed, 'station', 'station', 'unspecified')
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
        if not ed or not ed.data or not ed.data.get('event_details', None):
            return

        ed = ed.data['event_details']

        etime = event.event_time.astimezone(
            timezone.get_current_timezone())
        b = {'time': etime.strftime(EVENT_LIST_TIMESTAMP_FORMAT),
             'section': safe_get_choice(ed, 'fenceSection', 'fencesection', 'unspecified'),
             'species': safe_get_choice(ed, 'species', 'species', 'unspecified'),
             'animal_name': safe_get_choice(ed, 'animal_name', 'fencebreak_animalname', 'unspecified'),
             'reported_by': safe_get_choice(ed, 'reported_by', 'fencebreak_reportedby', 'unspecified'),
             'action': safe_get_choice(ed, 'actionTaken', 'fencebreak_actiontaken', 'unspecified'),
             'feedback': escape(ed.get('feedback', ''))
             }

        accum.append(b)

    fence_breakage = accumulator([], fence_breakage)

    # Accumulator for an event category
    def make_events_accum(categories):
        event_categories = categories

        def inner_events(accum, event):
            if event.event_type.category.value not in event_categories:
                return

            # Special case: exclude human_wildlife_conflict events which are to be included in another section of
            #               this report.
            if event.event_type.value in HWC_REPORT_TYPES:
                return

            event_details = schema_utils.generate_details(
                event, render_schema(event.event_type.schema))
            en = event.notes.all().order_by('created_at')

            def build_note(note):
                return {'text': html.escape(note.text),
                        'username': note.created_by_user.username,
                        'created_at': note.created_at.astimezone(timezone.get_current_timezone()).strftime(EVENT_LIST_TIMESTAMP_FORMAT),
                        }

            accum.append({'title': '{}: {}'.format(event.serial_number, escape(event.title)),
                          'event_name': '{}: {}'.format(event.serial_number, escape(event.title)),
                          'event_time': event.event_time.astimezone(timezone.get_current_timezone()).strftime(EVENT_LIST_TIMESTAMP_FORMAT),
                          'attributes': sorted(event_details, key=lambda x: x['order']),
                          'notes': [build_note(n) for n in en]
                          })
        return inner_events

    security_events = accumulator(
        [], make_events_accum(('security', 'security_new')))
    security_ke_police_events = accumulator(
        [], make_events_accum(('security_ke_police',)))
    findrep_events = accumulator(
        [], make_events_accum(('findrep_category',)))

    # Accumulator for 'human wildlife conflict'
    def human_wildlife_conflict(accum, event):
        if event.event_type.value not in HWC_REPORT_TYPES:
            return
        # ed = event.event_details.first()
        # if not ed or not ed.data or 'event_details' not in ed.data:
        #     return
        # ed = ed.data['event_details']

        event_details = schema_utils.generate_details(
            event, render_schema(event.event_type.schema))

        en = event.notes.all().order_by('created_at')

        def build_note(note):
            return {'text': html.escape(note.text),
                    'username': note.created_by_user.username,
                    'created_at': note.created_at.astimezone(timezone.get_current_timezone()).strftime(EVENT_LIST_TIMESTAMP_FORMAT),
                    }

        accum.append({'title': '{}: {}'.format(event.serial_number, escape(event.title)),
                      'event_name': '{}: {}'.format(event.serial_number, escape(event.title)),
                      'event_time': event.event_time.astimezone(timezone.get_current_timezone()).strftime(EVENT_LIST_TIMESTAMP_FORMAT),
                      'attributes': sorted(event_details, key=lambda x: x['order']),
                      'notes': [build_note(n) for n in en]
                      })

    human_wildlife_conflict = accumulator([], human_wildlife_conflict)
    b = broadcast((rhino_sightings, rhino_births, rhino_territorial_movement, other_wildlife_sightings, carcass,
                   gap_movement, rainfall, fence_breakage, security_events, security_ke_police_events, findrep_events, human_wildlife_conflict))

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
    security_ke_police_events = security_ke_police_events.send(None)
    findrep_events = findrep_events.send(None)
    human_wildlife_conflict = human_wildlife_conflict.send(None)

    #
    # Query for rhino sightings over the last 7 days, to determine which rhinos are 'missing' for
    # an inordinate time.
    #
    near_threshold = before - timedelta(days=3)
    far_threshold = before - timedelta(days=7)
    rhino_sighting_events = get_rhino_sightings(far_threshold, before)
    missing_rhinos = dict((str(r.id), {'name': escape(
        r.name), 'days_ago': 1000000}) for r in get_rhinos())

    for event in rhino_sighting_events:
        ed = event.event_details.first()
        if not ed or not ed.data or 'event_details' not in ed.data:
            continue
        ed = ed.data['event_details']

        rhinos_in_event = _listify(
            ed.get('blackRhinos')) + _listify(ed.get('whiteRhinos'))
        rhino_ids_in_event = [_.get('value') if isinstance(
            _, dict) else _ for _ in rhinos_in_event]

        for rhino_id in rhino_ids_in_event:
            if rhino_id:
                if event.event_time > near_threshold:
                    missing_rhinos.pop(rhino_id, None)
                else:
                    # Use Math.ceil(timedelta) to indicate 'days ago'. Ex.
                    # 3 days 5 hours => 4 days ago.
                    missing_rhinos[rhino_id]['days_ago'] = min(missing_rhinos[rhino_id]['days_ago'],
                                                               (before - event.event_time).days + 1)

    # Post-process missing rhinos.
    missing_rhinos = sorted(missing_rhinos.values(), key=lambda _: _[
        'days_ago'], reverse=True)
    for r in missing_rhinos:
        r['days_ago'] = '> 7' if r['days_ago'] > 7 else str(r['days_ago'])

    REPORT_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S %Z'
    REPORT_TIME_FORMAT = '%-d %B %Y %Z' if platform.system().lower() != 'windows' else '%#d %B %Y %Z'
    since_text = since.astimezone(
        timezone.get_current_timezone()).strftime(REPORT_TIMESTAMP_FORMAT)
    before_text = before.astimezone(
        timezone.get_current_timezone()).strftime(REPORT_TIMESTAMP_FORMAT)
    context = {
        'report_filename': 'Daily-SitRep-{}.docx'.format(before.astimezone(timezone.get_current_timezone())
                                                         .strftime('%Y-%m-%d')),
        'report_time': before.astimezone(timezone.get_current_timezone()).strftime(REPORT_TIME_FORMAT),
        'report_daterange_text': 'Including events from: {} to: {}'.format(since_text, before_text),
        'footer_text': 'Report generated by EarthRanger user {username} at {generated_at}'.format(
            generated_at=generated_at.strftime(REPORT_TIMESTAMP_FORMAT),
            username=kwargs.get('username') or 'system'),

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

        'security_ke_police_events': security_ke_police_events,

        'findrep_events': findrep_events,

        'human_wildlife_conflict': human_wildlife_conflict,

    }

    return context
