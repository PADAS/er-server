'''
  These functions are helpers, carried over from a previous alerting implementation.
'''

import logging
import urllib.parse

from django.utils.translation import gettext_lazy as _

sms_separator_string = '{0}: {1}'
email_separator_string = ' {0} {1}: {2}'

ignore_fields = ['sort_at', 'updated_at', 'created_at', 'updates', 'image_url',
                 'priority', 'geojson', 'location', 'event_details', 'id',
                 'serial_number', 'state', 'photos', 'is_contained_in', 'url',
                 'event_category', 'is_collection', 'attributes', 'provenance',
                 'priority_label', 'files', 'message', 'related_subjects']

# For each deep-link code that the iOS app recognizes, provide a list of
# event types.
event_type_code_map = {
    'immobility': ['immobility', 'immobility_all_clear', ],
    'geofence': ['geofence_break', 'geofence', ],
    'low-speed': ['low_speed_wilcoxon', 'low_speed_wilcoxon_all_clear',
                  'low_speed_percentile' 'low_speed_percentile_all_clear', ],
    'proximity': ['proximity', ],
}

logger = logging.getLogger(__name__)

# Reverse the map, to event-type -> deep-link code.
event_type_code_map = dict((v, k)
                           for k, l in event_type_code_map.items() for v in l)

#
# Helper functions below here.
#
DISPLAY_TRANLATION = {
    'event_type': _('Report Type'),
    'time': _('Created On'),
}


def fetch_latest_location(subject):
    """
    Fetch Subject's latest location.
    :return: Latest latitude, latest longitude, latest observation time.
    """
    try:
        from observations.models import Observation
        observation = Observation.objects.filter(
            source__subjectsource__subject=subject).order_by(
            '-recorded_at')[0]
        return str(observation.location.y), str(observation.location.x), \
            observation.recorded_at.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.info(e)
        return '', '', ''


def build_deep_link_for_subject(event, subject, default_event_code='panic',
                                last_lat=None, last_lon=None):
    """
    Deep link must look like this:

    steta://?event={type}&name={name}&sys={source}&t={timestamp}&lat={lat}&lon={lon}&id={subject_id}

    """
    link_data = {
        'event': event_type_code_map.get(event.event_type.value, default_event_code),
        'name': subject.name,
        'id': str(subject.id),
        'sys': 'das',
        't': event.time.strftime('%Y-%m-%dT%H:%M:%S'),
        'lon': str(event.location.x),
        'lat': str(event.location.y),
    }
    if last_lat and last_lon:
        link_data.update({'last_lat': last_lat, 'last_lon': last_lon})

    qs = '&'.join('='.join((k, urllib.parse.quote(v)))
                  for k, v in link_data.items())
    return '?'.join(('steta://', qs))
