from rest_framework.exceptions import APIException


class UnauthorizedView(APIException):
    """
    User does not have view permission, return empty data
    """

    status_code = 200
    default_detail = {"data": []}
