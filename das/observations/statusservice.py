# import logging
# from dateutil.parser import parse as parse_date
#
# from django.db.models import Case, CharField, Value, When, F, Q
# from django.db.models.functions import Greatest
# from django.contrib.gis.db import models as dbmodels
# from django.db import connection
# from django.contrib.gis.geos import Point
# from tracking.pubsub_registry import notify_new_tracks
#
# from observations.models import SubjectStatus
#
# logger = logging.getLogger(__name__)
#
# def ensure_subjectstatus_exists(subject_id, delay_hours=0):
#     SubjectStatus.objects.get_or_create(subject_id=subject_id, delay_hours=delay_hours)
#
#
# def update_subject_status_from_observation(observation, delay_hours=0):
#
#     status_updates = build_updates_from_observation(observation)
#
#     try:
#         SubjectStatus.objects.filter(subject__subjectsource__source=observation.source,
#                                      subjectsource__assigned_range__contains=observation.recorded_at,
#                                      delay_hours=delay_hours).update(
#             additional=observation.additional, **status_updates)
#         notify_new_tracks(observation.source.id)
#     finally:
#         logger.debug(connection.queries[-1])
#
#
# def update_subject_status_from_post(source, recorded_at, location, additional):
#     '''
#     Intention is to update latest SubjectStatus record under the case where a redundant GPS fix has been posted.
#     '''
#     status_updates = build_updates(recorded_at=recorded_at,
#                                    location=location,
#                                    radio_state=additional.get('radio_state'),
#                                    radio_state_at=additional.get('radio_state_at'),
#                                    last_voice_call_start_at=additional.get('last_voice_call_start_at'),
#                                    location_requested_at=additional.get('location_requested_at'))
#
#     try:
#         SubjectStatus.objects.filter(subject__subjectsource__source=source,
#                                      subjectsource__assigned_range__contains=recorded_at,
#                                      delay_hours=0).update(additional=additional, **status_updates)
#         notify_new_tracks(source.id)
#     finally:
#         logger.debug(connection.queries[-1])
#
#
# def build_updates_from_observation(observation):
#     '''
#     Build conditional updates from Observation model instance.
#     :param observation:
#     :return:
#     '''
#     data = observation.additional
#
#     radio_state = data.get('state', SubjectStatus.UNKNOWN)
#
#     if radio_state == 'online' and data['additional']['gps_fix']:
#         radio_state = '-'.join((radio_state, 'gps'))
#
#     return build_updates(recorded_at=observation.recorded_at,
#                          location={'longitude':observation.location.x,
#                                    'latitude': observation.location.y},
#                          radio_state=radio_state,
#                          radio_state_at=data['radio_state_at'],
#                          last_voice_call_start_at=data.get('last_voice_call_start_at'),
#                          location_requested_at=data.get('location_requested_at'))
#
#
# def build_updates(recorded_at, location, radio_state=None, radio_state_at=None,
#                   last_voice_call_start_at=None, location_requested_at=None):
#     '''
#     Build conditional updates from parsed observation attributes.
#     '''
#     location = Point(x=location['longitude'], y=location['latitude'], srid=4326)
#
#
#     conditional_updates = {
#         'recorded_at': Greatest(F('recorded_at'), Value(recorded_at) ),
#         'location': Case(
#             When(recorded_at__lt=Value(recorded_at), then=Value(str(location)) ),
#             default=F('location'),
#             # output_field=dbmodels.PointField()
#
#         ),
#     }
#
#     if radio_state_at:
#         try:
#             radio_state_at = parse_date(radio_state_at)
#             if radio_state:
#                 conditional_updates['radio_state'] = Case(
#                     When(radio_state_at__lt=Value(radio_state_at), then=Value(radio_state)),
#                     default=F('radio_state'), output_field=dbmodels.CharField())
#
#                 conditional_updates['radio_state_at'] = Greatest(F('radio_state_at'), Value(radio_state_at),
#                                                             output_field=dbmodels.DateTimeField())
#
#         except:
#             pass
#
#     if last_voice_call_start_at:
#         try:
#             last_voice_call_start_at = parse_date(last_voice_call_start_at)
#             conditional_updates['last_voice_call_start_at'] = Greatest(F('last_voice_call_start_at'),
#                                                                  Value(last_voice_call_start_at))
#         except:
#             pass
#
#     if location_requested_at:
#         try:
#             location_requested_at = parse_date(location_requested_at)
#             conditional_updates['location_requested_at'] = Greatest(F('location_requested_at'),
#                                                                  Value(location_requested_at))
#         except:
#             pass
#
#     return conditional_updates
#
#
