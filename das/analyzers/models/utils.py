from geopy.distance import distance
from shapely.geometry.multipoint import MultiPoint

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
