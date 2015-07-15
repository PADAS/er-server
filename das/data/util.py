import json
from types import GeneratorType
from itertools import chain
import uuid
import datetime

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
        elif isinstance(o, uuid.UUID):
            return str(o)
        elif isinstance(o, (GeneratorType, chain)):
            return [item for item in o]
        elif isinstance(o, JsonEncodedString):
            return o.data
        return json.JSONEncoder.default(self, o)


