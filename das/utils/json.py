import copy
import datetime
import json
import uuid
from itertools import chain
from types import GeneratorType

import dateutil.parser as dp
import simplejson
import six

from django.conf import settings

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

try:
    from django.contrib.gis.geos import Point
    geos_imported = True
except ImportError:
    geos_imported = False

try:
    import django.utils.functional as d_proxy
    d_proxy_imported = True
except ImportError:
    d_proxy_imported = False

from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer


class JsonEncodedString(object):
    """A python class that contains a string that is json encoded.
    This class is recognized in our ExtendedJSONEncode"""

    def __init__(self, data):
        self.data = data


def date_to_isoformat(o):
    datetime.MINYEAR
    if not hasattr(o, 'second'):
        tmpval = datetime.datetime(o.year, o.month, o.day)
        formatted_value = tmpval.isoformat()
    else:
        formatted_value = o.isoformat() if o.microsecond is None \
            else o.replace(microsecond=0).isoformat()
    return formatted_value


class ExtendedJSONEncoder(simplejson.JSONEncoder):
    def _iterencode_default(self, o, markers=None):
        if isinstance(o, JsonEncodedString):
            return o.data
        return simplejson.JSONEncoder._iterencode_default(self, o, markers)

    def default(self, o):  # pylint: disable-msg=E0202
        if isinstance(o, (datetime.datetime, datetime.date)):
            return date_to_isoformat(o)
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
        elif geos_imported and isinstance(o, Point):
            return o.tuple
        elif d_proxy_imported and isinstance(o, d_proxy.Promise):
            return str(o)
        return simplejson.JSONEncoder.default(self, o)


class ExtendedGEOJSONRenderer(JSONRenderer):
    """
    Don't wrap the return with a data and status block.
    """
    encoder_class = ExtendedJSONEncoder

    def render(self, data, *args, **kwargs):
        return super().render(data, *args, **kwargs)


class ExtendedJSONRenderer(JSONRenderer):
    encoder_class = ExtendedJSONEncoder

    def render(self, data, *args, **kwargs):
        response = args[1]['response']

        # Some responses will have data=None (Ex. 204 No Content)
        if not data or ('swaggerVersion' not in data and 'status' not in data):
            data = {'data': data,
                    'status': {'code': response.status_code,
                               'message': response.status_text}}
        return super(ExtendedJSONRenderer, self).render(data, *args, **kwargs)


class JSONTextParser(BaseParser):
    """
    Parses JSON-serialized data sent with a text/json content type.
    """
    media_type = 'text/json'
    renderer_class = JSONRenderer

    def parse(self, stream, media_type=None, parser_context=None):
        """
        Parses the incoming bytestream as JSON and returns the resulting data.
        """
        parser_context = parser_context or {}
        encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)

        try:
            data = stream.read().decode(encoding)
            return json.loads(data)
        except ValueError as exc:
            raise ParseError('JSON parse error - %s' % six.text_type(exc))


class ExtendedBrowsableAPIRenderer(BrowsableAPIRenderer):
    def render(self, data, *args, **kwargs):
        response = args[1]['response']

        # Some responses will have data=None (Ex. 204 No Content)
        if not data or 'status' not in data:
            data = {'data': data,
                    'status': {'code': response.status_code,
                               'message': response.status_text}}
        return super(ExtendedBrowsableAPIRenderer, self).render(data, *args, **kwargs)


def dumps(obj, **kwargs):
    dumps_args = copy.copy(kwargs)
    custom_args = dict(cls=ExtendedJSONEncoder, ensure_ascii=True,
                       bigint_as_string=True)
    dumps_args.update(custom_args)
    return simplejson.dumps(obj, **dumps_args)


def loads(s, **kwargs):
    return simplejson.loads(s, **kwargs)


def parse_bool(text):
    """Return a boolean from the passed in text"""
    TRUE_VALUES = ['true', '1', 'yes', 'ok', 'okay']
    if isinstance(text, bool):
        return text
    if isinstance(text, str) and text.lower() in TRUE_VALUES:
        return True
    return False


def json_string(objects, pretty_output=False):
    """Encode python objects into a json string.
    The encoder is: date and mongo object aware.
    The result is in UTF-8 encoded by default, set your
    charset=UTF-8
    """
    if pretty_output is True:
        return simplejson.dumps(objects, sort_keys=True, indent=4,
                                cls=ExtendedJSONEncoder, ensure_ascii=True, bigint_as_string=True)
    return simplejson.dumps(objects, cls=ExtendedJSONEncoder, ensure_ascii=True, bigint_as_string=True)


def empty_geojson_featurecollection():
    return {
        "type": "FeatureCollection",
        "features": []
    }


def empty_geojson_feature():
    return {
        "type": "Feature",
        "geometry": {},
        "properties": {}
    }


def zeroout_microseconds(value):
    if (not value or not hasattr(value, 'microsecond') or
            value.microsecond is None):
        return value
    return value.replace(microsecond=0)


class DateTimeAwareJSONEncoder(json.JSONEncoder):
    """
    Converts a python object, where datetime and timedelta objects are converted
    into objects that can be decoded using the DateTimeAwareJSONDecoder.
    """

    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return {
                '__type__': 'datetime',
                'value': obj.isoformat(),
            }

        elif isinstance(obj, datetime.timedelta):
            return {
                '__type__': 'timedelta',
                'days': obj.days,
                'seconds': obj.seconds,
                'microseconds': obj.microseconds,
            }

        else:
            return json.JSONEncoder.default(self, obj)


class DateTimeAwareJSONDecoder(json.JSONDecoder):
    """
    Converts a json string, where datetime and timedelta objects were converted
    into objects using the DateTimeAwareJSONEncoder, back into a python object.
    """

    def __init__(self):
        json.JSONDecoder.__init__(self, object_hook=self.dict_to_object)

    def dict_to_object(self, d):
        if '__type__' not in d:
            return d

        type = d.get('__type__')
        if type == 'datetime':
            return dp.parse(d['value'])
        elif type == 'timedelta':
            d.pop('__type__', None)
            return datetime.timedelta(**d)
        else:
            return d
