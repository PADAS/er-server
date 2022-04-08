import logging

from django.contrib.gis.geos import MultiPolygon, Point, Polygon

logger = logging.getLogger(__name__)


def validate_bbox(bbox_as_string):
    """
    :param
        bbox_as_string: a comma-delimited string describing the bbox corners. it should be positionally spcecified as:
            southWest.long,southWest.lat,northEast.long,northEast.lat
    :return:
        if input bbox does not crosses the IDL, then a Polygon representing the input params is returned.
        if IDL is crossed, a MultiPolygon is returned instead with each piece to the left and right of the IDL.
    """
    bbox = bbox_as_string.split(',')
    bbox = [float(v) for v in bbox]
    if len(bbox) != 4:
        raise ValueError("invalid bbox param")

    if bbox[0] < -180:
        if bbox[2] > -180:
            left_bbox = Polygon.from_bbox(
                [bbox[0] + 360, bbox[1], 180, bbox[3]])
            right_bbox = Polygon.from_bbox([-180, bbox[1], bbox[2], bbox[3]])
            poly = MultiPolygon(left_bbox, right_bbox)
        else:
            poly = Polygon.from_bbox(
                [bbox[0] + 360, bbox[1], bbox[2] + 360, bbox[3]])
    elif bbox[2] > 180:
        if bbox[0] < 180:
            left_bbox = Polygon.from_bbox([bbox[0], bbox[1], 180, bbox[3]])
            right_bbox = Polygon.from_bbox(
                [-180, bbox[1], bbox[2] - 360, bbox[3]])
            poly = MultiPolygon(left_bbox, right_bbox)
        else:
            poly = Polygon.from_bbox(
                [bbox[0] - 360, bbox[1], bbox[2] - 360, bbox[3]])
    else:
        poly = Polygon.from_bbox(bbox)

    return poly


def points_cross_idl(point1, point2):
    '''
    :params:
        point1 the first point as a tuple to test
        point2 the second point to test against point1 to see if they cross the IDL

    :return:
        if the two input points cross the international date line (IDL), True is returned
        otherwise, False is returned
    '''

    return (point2[0] - point1[0]) > 180


def convert_to_point(location):
    """Convert the location to a Point geometry object.

    Args:
        location (str, dict, Point): accept a string that is comma delimited latitude, longitude values. Alternatively aceepts a dictionary with "latitude" and "longitude" keys.

    Raises:
        TypeError: if location is not str, dict or Point

    Returns:
        Point: the converted value
    """
    if isinstance(location, Point):
        pass
    elif isinstance(location, str):
        latitude = float(location.split(",")[0].strip())
        longitude = float(location.split(",")[1].strip())
        location = Point(longitude, latitude, srid=4326)
    elif isinstance(location, dict):
        location = Point(location['longitude'],
                         location['latitude'])
    else:
        raise TypeError(f"Unexpected type for location: {location}")
    return location
