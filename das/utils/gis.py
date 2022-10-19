import logging
import math

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point, Polygon

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
        location (str, dict, Point): accept a string that is comma delimited longitude, latitude values.
        Alternatively accepts a dictionary with "longitude" and "latitude" keys.

    Raises:
        TypeError: if location is not str, dict or Point

    Returns:
        Point: the converted value
    """
    if isinstance(location, Point):
        pass
    elif isinstance(location, str):
        longitude = float(location.split(",")[0].strip())
        latitude = float(location.split(",")[1].strip())
        location = Point(longitude, latitude, srid=4326)
    elif isinstance(location, dict):
        location = Point(location['longitude'], location['latitude'])
    else:
        raise TypeError(f"Unexpected type for location: {location}")
    return location


def get_utm_by_wgs_84(longitude: float, latitude: float) -> int:
    """
    This solution was taken from:
    Source: https://stackoverflow.com/questions/68220763/geodjango-calculate-and-save-polygon-area-in-units-upon-object-creation
    """
    utm_zone_num = int(math.floor((longitude + 180) / 6) + 1)
    utm_zone_hemi = 6 if latitude >= 0 else 7
    utm_epsg = 32000 + utm_zone_hemi * 100 + utm_zone_num
    return utm_epsg


def get_polygon_info(geom: GEOSGeometry, key: str = "area") -> float:
    """
    It takes a geometry, transforms it to a given EPSG, and returns the value of a given attribute.
    NOTE: For get the perimeter us the key "length"

    Returns:
      The perimeter or area of the polygon in meters or square meters.
    """
    epsg = get_utm_by_wgs_84(geom.centroid.x, geom.centroid.y)
    transformed_geo = geom.transform(epsg, clone=True)
    return round(getattr(transformed_geo, key), 2)
