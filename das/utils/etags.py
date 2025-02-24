import hashlib
from typing import Dict, Optional, Union

from django.contrib.gis.db.models import Model, QuerySet
from django.core.exceptions import ValidationError
from django.core.handlers.wsgi import WSGIRequest
from rest_framework.request import Request

HEADERS_LIST_USED = ["user-profile"]


def generate_etag_string(original_string: str, request: Union[Request, WSGIRequest]) -> str:
    """
    Generate an ETag string by hashing the original string with additional salting based on request headers and user ID.

    Args:
        original_string (str): The original string to be hashed.
        request (Union[Request, WSGIRequest]): The request object containing headers and user information.

    Returns:
        str: The generated ETag string as an MD5 hash.
    """
    string_to_be_hashed = _salt_string_to_hash(string_to_be_hashed=original_string, request=request)
    return hashlib.md5(string_to_be_hashed.encode("utf-8")).hexdigest()


def get_hash_from_queryset(
    queryset: QuerySet, request: Union[Request, WSGIRequest], extra_salt: Optional[str] = None
) -> str:
    """
    Generate a hash from a Django QuerySet.

    This function converts the QuerySet to a string, salts it with request headers and user ID,
    and then generates an MD5 hash from the salted string.

    Args:
        queryset (QuerySet): The Django QuerySet to be hashed.
        request (Union[Request, WSGIRequest]): The request object containing headers and user information.

    Returns:
        str: The generated hash as an MD5 hash.
    """
    if not queryset._fields:
        raise ValidationError(message="Invalid QuerySet: The QuerySet is defined without a list of values.")

    queryset_string = str(list(queryset))
    string_to_be_hashed = _salt_string_to_hash(queryset_string, request, extra_salt)
    return _generate_hash_from_string(string_to_be_hashed)


def get_hash_from_model_instance(
    model_instance: Union[Model, Dict[str, str]], request: Union[Request, WSGIRequest], extra_salt: Optional[str] = None
) -> str:
    """
    Generate a hash from a Django model instance.

    This function converts the model instance to a string, salts it with request headers and user ID,
    and then generates an MD5 hash from the salted string.

    Args:
        model_instance (Union[QuerySet, Dict[str, str]]): The Django model instance to be hashed.
        request (Union[Request, WSGIRequest]): The request object containing headers and user information.

    Returns:
        str: The generated hash as an MD5 hash.
    """
    # Get ordered list of fields from the model instance.
    if isinstance(model_instance, Model):
        fields = [field.name for field in model_instance._meta.concrete_fields]
        model_instance = {field: getattr(model_instance, field) for field in fields}

    model_instance_string = str(model_instance)
    string_to_be_hashed = _salt_string_to_hash(model_instance_string, request, extra_salt)
    return _generate_hash_from_string(string_to_be_hashed)


def _generate_hash_from_string(string_to_be_hashed: str) -> str:
    return hashlib.md5(string_to_be_hashed.encode("utf-8")).hexdigest()


def _get_headers(request: Union[Request, WSGIRequest]) -> Dict[str, str]:
    headers = {}

    for header_name in HEADERS_LIST_USED:
        header_property = request.headers.get(header_name, None)
        if header_property:
            headers[header_name] = header_property
    return headers


def _salt_string_to_hash(
    string_to_be_hashed: str, request: Union[Request, WSGIRequest], extra_salt: Optional[str] = None
) -> str:
    headers = _get_headers(request)
    if headers:
        for header in headers:
            string_to_be_hashed += f":{header}:{headers[header]}"
    string_to_be_hashed += f":{request.user.id}"
    if extra_salt:
        string_to_be_hashed += f":{extra_salt}"
    return string_to_be_hashed
