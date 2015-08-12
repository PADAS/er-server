import uuid
import datetime
from itertools import islice, chain
from types import GeneratorType
import simplejson as json
try:
    import psycopg2.extras
    psycopg2_imported = True
except ImportError:
    psycopg2_imported = False

try:
    from bson import ObjectId
    bson_imported = True
except ImportError:
    bson_imported = False

class JsonEncodedString(object):
    """A python class that contains a string that is json encoded.
    This class is recognized in our ExtendedJSONEncode"""
    def __init__(self, data):
        self.data = data

class ExtendedJSONEncoder(json.JSONEncoder):
    def _iterencode_default(self, o, markers=None):
        if isinstance(o, JsonEncodedString):
            return o.data
        return json.JSONEncoder._iterencode_default(self, o, markers)

    def default(self, o):# pylint: disable-msg=E0202
        if isinstance(o, (datetime.datetime, datetime.date)):
            datetime.MINYEAR
            if not hasattr(o, 'second'):
                tmpval = datetime.datetime(o.year, o.month, o.day)
                formatted_value = tmpval.isoformat()
            else:
                formatted_value = o.isoformat()
            return formatted_value
        elif bson_imported and isinstance(o, ObjectId):
            # needed for supporting the MongoDB ObjectId
            return """{u'$oid': u'%s'}""" % str(o)
        elif isinstance(o, (psycopg2.extras.DateTimeTZRange,)):
            return [o.lower, o.upper]
        elif isinstance(o, uuid.UUID):
            return str(o)
        elif isinstance(o, (GeneratorType, chain)):
            return [item for item in o]
        elif isinstance(o, JsonEncodedString):
            return o.data
        return json.JSONEncoder.default(self, o)


def json_string(objects, pretty_output=False):
    """Encode python objects into a json string.
    The encoder is: date and mongo object aware.
    The result is in UTF-8 encoded by default, set your
    charset=UTF-8
    """
    if pretty_output is True:
        return json.dumps(objects, sort_keys=True, indent=4,
                      cls=ExtendedJSONEncoder, ensure_ascii=True, bigint_as_string=True)
    return json.dumps(objects, cls=ExtendedJSONEncoder, ensure_ascii=True, bigint_as_string=True)


def empty_geojson_featurecollection():
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": []
        }


def empty_geojson_feature():
    return {
        "type": "Feature",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "geometry": {}
        }