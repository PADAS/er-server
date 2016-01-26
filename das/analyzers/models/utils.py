from geopy.distance import distance

def distance_to_exterior_point(polygon, point):
    """ for a point outside polygon, return the distance in meters
    to that point """
    d = polygon.boundary.project(point)
    p = polygon.boundary.interpolate(d)
    return distance(p.coords, point.coords).m
