import copy
import logging
import urllib.parse as parser

from django.contrib.auth import get_user_model
from django.http.request import HttpRequest
from geopy.distance import distance
from shapely.geometry.multipoint import MultiPoint

from activity.models import Event
from activity.serializers import EventSerializer

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


def get_geostore_id(download_url):
    qs = parser.parse_qs(parser.urlparse(download_url).query)
    return qs.get('geostore', [''])[0]


def build_confirmed_url_with_geostore_id(download_url, geostore_id):
    query_params = parser.parse_qs(parser.urlparse(download_url).query)
    # update the geostore & gladConfirmOnly in the query string
    query_params['geostore'][0] = geostore_id
    query_params['gladConfirmOnly'][0] = True
    parsed_result = parser.urlparse(download_url)
    # create and return a new url
    new_parsed_result = parser.ParseResult(scheme=parsed_result.scheme, netloc=parsed_result.netloc,
                                           path=parsed_result.path, params=parsed_result.params,
                                           fragment=parsed_result.fragment,
                                           query=parser.urlencode(query_params, doseq=True))
    return parser.urlunparse(new_parsed_result)
