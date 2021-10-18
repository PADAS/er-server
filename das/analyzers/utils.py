import copy
import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.http.request import HttpRequest
from geopy.distance import distance
from shapely.geometry.multipoint import MultiPoint

from activity.models import Event
from activity.serializers import EventSerializer
from analyzers.base import SubjectAnalyzer
from observations.models import Subject

logger = logging.getLogger(__name__)


def latest_event_for(analyzer):
    """ Returns the most recent event or None for a given subject and analyzer """

    event = Event.objects \
        .filter(
            provenance='analyzer',
            attributes__analyzer_id=analyzer.id) \
        .order_by('-created_at') \
        .first()

    return event


def distance_to_exterior_point(polygon, point):
    """ for a point outside polygon, return the distance in meters
    to that point """
    d = polygon.boundary.project(point)
    p = polygon.boundary.interpolate(d)
    return distance(p.coords, point.coords).m


def cluster(track, radius):
    """ returns the probability (in the range 0-1 inclusive) of a
    track being clustered to radius. """

    centroid = MultiPoint(track.geo_series).centroid
    num_points = len(track.geo_series)
    inside_points = []
    for point in track.geo_series:
        distance_meters = distance(point.coords, centroid.coords).m
        if distance_meters <= radius:
            inside_points.append(point)

    probability = len(inside_points) / num_points

    return probability


def get_system_user():
    User = get_user_model()
    user, created = User.objects.get_or_create(username='system_analyzers',
                                               defaults=dict(last_name='Alyzer', first_name='Anne',
                                                             email='system_analyzers@pamdas.org',
                                                             is_active=False,
                                                             password=User.objects.make_random_password()))
    return user


def save_analyzer_event(event_data):

    # TODO: I create a blank request here, in order to provide
    # EventSerializer with a valid context that includes a User.

    request = HttpRequest()
    request.user = get_system_user()
    ser = EventSerializer(data=event_data,
                          context={'request': request})

    if ser.is_valid():
        logger.info('Saving analyzer event.', extra=event_data)
        return ser.create(ser.validated_data)

    raise ValueError('Analyzer Event is invalid, errors=%s' % (ser.errors,))


def typify(fmap, item):
    '''
    Convenience method to convert values in 'item' using a dict of key, func pairs
    :param fmap: key=>func, where key is a key within item and func is to be applied to the corresponding value in item.
    :param item: A dictionary to which we'll apply the functions.
    :return: A new dict
    '''

    r = copy.copy(item)
    for k, f in fmap.items():
        r[k] = f(r[k])
    return r


def get_analyzer_key(analyzer: SubjectAnalyzer, subject: Subject) -> Optional[str]:
    if analyzer.config.quiet_period:
        return f"analyzer_silent__{analyzer.config.id}__{subject.id}"
    return None
