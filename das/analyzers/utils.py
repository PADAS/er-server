from geopy.distance import distance
from shapely.geometry.multipoint import MultiPoint

from activity.models import Event

from analyzers.immobility import ImmobilityAnalyzer

subject_analyzers = (ImmobilityAnalyzer,)


def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)


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
