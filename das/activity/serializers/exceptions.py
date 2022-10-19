from django.utils.encoding import force_str
from rest_framework.exceptions import APIException
from rest_framework.status import HTTP_409_CONFLICT


class DuplicateResourceException(APIException):
    default_status_code = HTTP_409_CONFLICT
    default_fieldname = "unknown field"
    default_detail = "The resource provided conflicts with an existing resource."

    def __init__(self, fieldname=None, detail=None, status_code=None):
        self.status_code = status_code or self.default_status_code
        self.detail = {fieldname or self.default_fieldname: force_str(detail or self.default_detail)}
