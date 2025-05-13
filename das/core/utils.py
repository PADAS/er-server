import hashlib
import json
import logging
import re
import time
import urllib.parse
import uuid
from collections import namedtuple
from datetime import datetime
from typing import Dict

import jsonschema
import pytz

from django.apps.registry import Apps
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.cache import caches
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.db import connection
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.http.request import HttpRequest
from django.utils import timezone
from django.utils.dateparse import parse_duration
from django.utils.functional import cached_property

from core.models import DASTenant
from utils.constants import regex
from utils.tenant import TenantNotFoundException
from utils.tenant.managers import UnsetDASTenantContextManager
from utils.tenant.providers import TenantData

logger = logging.getLogger(__name__)


class StaticImageFinder(object):
    image_caches = {}
    IMAGE_TYPES = ("svg", "png", "jpg")
    StaticImage = namedtuple("StaticImage", ("exists", "path"))
    static_paths = ("{0}", "sprite-src/{0}")
    web_path = "/static/{0}"
    file_format = "{key}.{type}"

    def get_marker_icon(self, keys, image_types=IMAGE_TYPES):
        image_cache = self.image_caches.setdefault(image_types, {})

        for key in keys:
            static_image = image_cache.get(key, None)
            if static_image:
                if static_image.exists:
                    return static_image.path
                continue
            for t in image_types:
                file = self.file_format.format(**dict(key=key, type=t))
                for static_path in self.static_paths:
                    static_file = static_path.format(file)
                    try:
                        if staticfiles_storage.exists(static_file):
                            path = self.web_path.format(static_file)
                            image_cache[key] = self.StaticImage(True, path)
                            return path
                    except SuspiciousFileOperation:
                        pass
            image_cache[key] = self.StaticImage(False, None)


static_image_finder = StaticImageFinder()


class DirectoryIconFinder:
    """Singleton class to find icons in a directory whith cached results on instance and class level."""

    _instance = None
    _cache = caches["default"]

    def __new__(cls, dir_name="sprite-src", timeout=3600 * 24):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.dir_name = dir_name
            cls._instance.timeout = timeout
        return cls._instance

    @cached_property
    def _file_metadata(self):
        usercontent_conf = getattr(settings, "USERCONTENT_SETTINGS", {})
        allowed_extentions = usercontent_conf.get("imagefile_extensions", ("jpg", "jpeg", "png", "gif", "tif", "tiff"))

        try:
            _, filenames = staticfiles_storage.listdir(self.dir_name)
            return tuple(
                (f, staticfiles_storage.get_modified_time(f"{self.dir_name}/{f}"))
                for f in sorted(filenames)
                if f.split(".")[-1].lower() in allowed_extentions
            )
        except ValueError:
            return tuple()

        except Exception as e:
            logger.error(f"Error listing files in {self.dir_name}: {e}")
            raise e

    @classmethod
    def get_etag(cls, request=None, *args, **kwargs):
        instance = cls()
        cache_key = f"icons-etag-{cls._instance.dir_name}"
        etag = instance._cache.get(cache_key)

        if etag is None:
            etag = hashlib.md5(str(instance._file_metadata).encode()).hexdigest()
            cls._cache.set(cache_key, etag, timeout=cls._instance.timeout)
        return etag


class Schedule:
    def __init__(self, periods: Dict[str, list]):
        self.schedule_definition = periods

    def __contains__(self, value):
        raise NotImplemented("An extending class must implement __contains__.")

    def __repr__(self):
        return json.dumps(self.schedule_definition)


class OneWeekSchedule(Schedule):
    """
    A OneWeekSchedule is defined by a dictionary whereby each property is the name of a day of the week. Each
    value is a list of tuples where each tuple indicates a range of time of the form ('hh:mm', 'hh:mm').
    An example range is: ('08:30', '14:00') to represent a range from 8:30am to 2:00pm.

    A complete example is:
        {
          "schedule_type": "week",
          "periods":
            {
                "monday": [["08:00", "12:00"], ["13:00", "17:30"]],
                "wednesday": [["08:00", "12:00"], ["13:00", "17:30"]]
            }
        }

    Once initialized you can ask if a datetime is in the Schedule.
    """

    # List of days compatible with ISO weekday index.
    days_of_week = ["index-0", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    def __init__(self, schedule_definition: Dict[str, dict] = dict):
        self.schedule_definition = schedule_definition or {}

        if self.schedule_definition:
            self.validate_schedule_document()

        self.schedule_periods = self.schedule_definition.get("periods", {})

        if "timezone" in self.schedule_definition:
            self.schedule_timezone = pytz.timezone(self.schedule_definition["timezone"])
        else:
            self.schedule_timezone = timezone.get_current_timezone()

    def __contains__(self, value):
        if not bool(self.schedule_periods):
            return True

        value = value.astimezone(self.schedule_timezone)

        # Truncate the timestamp to our finest granularity.
        value = value.replace(second=0, microsecond=0)

        relevant_periods = self.schedule_periods.get(self.days_of_week[value.isoweekday()])
        if relevant_periods:
            return self.test_timestamp(value, relevant_periods)
        return False

    def test_timestamp(self, sample_ts, periods):
        if not isinstance(sample_ts, datetime):
            return ValueError(f"Type {type(sample_ts)} is not supported.")

        # Calculate sample's total seconds for the day.
        ts_seconds = (sample_ts - sample_ts.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()

        for x, y in self._generate_ranges(periods):
            if x <= ts_seconds and ts_seconds <= y:  # inclusive
                return True
        return False

    @staticmethod
    def _generate_ranges(periods):
        for period in periods:
            start, end = (parse_duration(f"{x}:00") for x in period)
            yield (start.seconds, end.seconds)

    def validate_schedule_document(self):
        jsonschema.validate(self.schedule_definition, self.json_schema)

    json_schema = {
        "definitions": {
            "dayofweek": {
                "$id": "#/properties/periods/properties/dayofweek_periods",
                "type": "array",
                "title": "Day of week periods Schema",
                "default": None,
                "items": {
                    "$id": "#/properties/periods/properties/dayofweek/items",
                    "type": "array",
                    "title": "Time-based periods Schema",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {
                        "$id": "#/properties/periods/properties/dayofweek/items/items",
                        "type": "string",
                        "title": "Time-range Schema",
                        "default": "",
                        "examples": [
                            "08:00",
                            "17:30",
                        ],
                        "minLength": 5,
                        "maxLength": 5,
                        "pattern": "^[0-2]\\d:[0-5]\\d$",
                    },
                },
            }
        },
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://earthranger.com/schedule.json",
        "type": "object",
        "title": "The Schedule Schema",
        "additionalProperties": False,
        "properties": {
            "schedule_type": {
                "$id": "#/properties/schedule_type",
                "type": "string",
                "default": "week",
                "enum": ["week"],
                "title": "The kind of schedule this document represents. Currently only 'week' is supported.",
            },
            "periods": {
                "$id": "#/properties/schedule/periods",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "monday": {"$ref": "#/definitions/dayofweek"},
                    "tuesday": {"$ref": "#/definitions/dayofweek"},
                    "wednesday": {"$ref": "#/definitions/dayofweek"},
                    "thursday": {"$ref": "#/definitions/dayofweek"},
                    "friday": {"$ref": "#/definitions/dayofweek"},
                    "saturday": {"$ref": "#/definitions/dayofweek"},
                    "sunday": {"$ref": "#/definitions/dayofweek"},
                },
            },
            "timezone": {
                "$id": "#/properties/timezone",
                "type": "string",
                "title": "The name of the timezone within which the schedule will be evaluated.",
                "enum": list(pytz.all_timezones_set),
            },
        },
    }


class NonHttpRequest(HttpRequest):
    """
    This is a simple convenient class with minimal support for satisfying serialization
    outside an actual request.
    """

    def build_absolute_uri(self, url):
        if hasattr(settings, "UI_SITE_URL"):
            return f"{settings.UI_SITE_URL}{url}"
        return url


def get_site_name():
    """The sites name as used in google analytics and our ER site metrics"""
    if hasattr(settings, "METRICS_SITE_NAME"):
        return settings.METRICS_SITE_NAME

    if hasattr(settings, "UI_SITE_URL"):
        parts = urllib.parse.urlsplit(settings.UI_SITE_URL)
        sitename = parts.netloc.split(".")[0]
        return sitename
    return "unknown"


def is_uuid(string: str) -> bool:
    if isinstance(string, str):
        pattern = re.compile(rf"{regex.UUID}$", re.IGNORECASE)
        return bool(re.match(pattern, string))
    return False


class DASTenantManagement:
    def __init__(self, domain: str):
        self.domain = domain.split(":")[0]

    def get_or_create_tenant(self):
        tenant = self._get_existing_tenant()
        if not tenant:
            tenant_data = self._get_tenant_from_tms(domain=self.domain)
            try:
                with UnsetDASTenantContextManager():
                    tenant, _ = DASTenant.objects.get_or_create(
                        id=uuid.UUID(tenant_data["id"]), domain=tenant_data["domain"]
                    )
            except ValidationError:
                raise TenantNotFoundException(domain=self.domain)
        return tenant

    def get_tenant_id(self):
        tenant_data = self._get_tenant_from_tms(domain=self.domain)
        return tenant_data["id"]

    def _get_existing_tenant(self):
        with UnsetDASTenantContextManager():
            return DASTenant.objects.filter(domain=self.domain).first()

    def _get_tenant_from_tms(self, domain: str):
        instance = TenantData(domain=domain)
        return instance.get_tenant_data()


def update_tenant_models(models: list, tenant) -> None:
    """Batch update all records in every model with this tenant. Only
    updates rows that have a null tenant id.
    We use the django-fast-update library which is optimized to use postgresql
    temp tables for staging and applying updates.
    This function is only needed as we upgrade exisiting databases to MT. When we delete this
    function, stop installing the library.

    Args:
        models (list): list of models to ensure all records have a tenant id set
        tenant (_type_): the tenant
    """
    from fast_update.copy import copy_update

    batch_size = 10000

    table_exception_list = set(
        ["observations_subject", "observations_socketclient", "observations_usersession", "mapping_spatialfeaturegroup"]
    )
    pk_overrides = {"observations_socketclient": "sid", "observations_usersession": "sid"}

    with UnsetDASTenantContextManager():
        for class_model in models:
            start = time.time()
            logger.info("Backfilling das_tenant on model %s", class_model._meta.object_name)
            if class_model._meta.db_table in table_exception_list:
                cnt = class_model.objects.filter(das_tenant__isnull=True).update(das_tenant=tenant)
                total_seconds = time.time() - start
                logger.info(
                    "%d objects updated of model %s. In %.3f seconds", cnt, class_model._meta.object_name, total_seconds
                )
            else:
                qs = class_model.objects.filter(das_tenant__isnull=True)
                cnt = 0
                batch = []
                pk_name = pk_overrides.get(class_model._meta.db_table, "pk")
                for id in class_model.objects.filter(das_tenant__isnull=True).values_list(pk_name, flat=True):
                    cnt += 1
                    batch.append(class_model(**{pk_name: id, "das_tenant": tenant}))
                    if 0 == cnt % batch_size:
                        copy_update(qs=qs, objs=batch, fieldnames=("das_tenant",))
                        batch = []
                if batch:
                    copy_update(qs=qs, objs=batch, fieldnames=("das_tenant",))

                total_seconds = time.time() - start
                logger.info(
                    "%d objects updated of model %s. In %.3f seconds", cnt, class_model._meta.object_name, total_seconds
                )


def backfill_through_model_with_tenant(
    from_table_name: str,
    from_id_field: str,
    through_table_name: str,
    through_from_id_field: str,
    apps: Apps,
    schema_editor: BaseDatabaseSchemaEditor,
):
    backfill_sql = f"""
        WITH through_updates AS (
            SELECT tt.{through_from_id_field}, f.das_tenant_id
            FROM {through_table_name} tt
            JOIN {from_table_name} f ON tt.{through_from_id_field} = f.{from_id_field}
        )
        UPDATE {through_table_name} tt
        SET das_tenant_id = tu.das_tenant_id
        FROM through_updates tu
        WHERE tt.{through_from_id_field} = tu.{through_from_id_field};
        """
    with connection.cursor() as cursor:
        cursor.execute(backfill_sql)
