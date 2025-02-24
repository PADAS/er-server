import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any, Callable, Iterable, Optional

from django.contrib.auth.models import User
from django.contrib.gis.db.models import Model
from django.db.models import QuerySet
from django.http import QueryDict

from activity.models import EventType, PatrolType
from activity.views.events.utils import EventTypeQuerysetMixin
from utils.etags import get_hash_from_queryset
from utils.schema_utils import get_schema_renderer_method

logger = logging.getLogger(__name__)

PATROL_TYPE_FIELDS = (
    "value",
    "display",
    "ordernum",
    "icon_id",
    "is_active",
    "default_priority",
    "updated_at",
    "image_url",
)
EVENT_TYPE_FIELDS = (
    "updated_at",
    "category",
    "default_priority",
    "default_state",
    "display",
    "geometry_type",
    "icon",
    "is_active",
    "is_collection",
    "ordernum",
    "schema",
    "value",
)
SUBJECT_FIELDS = (
    "id",
    "name",
    "owner",
    "linked_user",
    "additional",
    "is_active",
    "common_name",
    "subject_subtype",
    "das_tenant",
)
EVENT_CATEGORY_FIELDS = (
    "display",
    "value",
    "ordernum",
    "is_active",
    "flag",
    "updated_at",
)
EVENT_TYPE_CATEGORIES_FIELDS = tuple(f"category__{field}" for field in EVENT_CATEGORY_FIELDS)
EVENT_TYPE_FIELDS_FOR_ETAG = list(EVENT_TYPE_FIELDS + EVENT_TYPE_CATEGORIES_FIELDS)


@dataclass
class Request:
    user: User
    query_params: QueryDict


class EventTypeQueryset(EventTypeQuerysetMixin):
    def __init__(self, user: Any, query_params: QueryDict):
        self.request = Request(user=user, query_params=query_params)


def build_patrol_type_etag_header(*args, **kwargs) -> str:
    patrol_type_to_string = partial(concatenate_fields_from_model, PATROL_TYPE_FIELDS)
    queryset = PatrolType.objects.filter(id=kwargs["id"])
    return build_etag_header(patrol_type_to_string, queryset)


def build_patrol_type_last_modified_header(*args, **kwargs) -> datetime:
    queryset = PatrolType.objects.filter(id=kwargs["id"])
    return get_most_recent_update_datetime_by_queryset(queryset)


def build_patrol_types_etag_header(*args, **kwargs) -> str:
    patrol_type_to_string = partial(concatenate_fields_from_model, PATROL_TYPE_FIELDS)
    return build_etag_header(patrol_type_to_string, PatrolType.objects)


def build_patrol_types_last_modified_header(*args, **kwargs) -> datetime:
    return get_most_recent_update_datetime_by_queryset(PatrolType.objects)


def build_event_types_etag_header(request, *args, **kwargs) -> str:
    queryset_builder = EventTypeQueryset(request.user, request.GET)
    queryset = queryset_builder.get_queryset()
    queryset = queryset.values(*EVENT_TYPE_FIELDS_FOR_ETAG)
    schemas = []
    for event_type in queryset:
        try:
            schemas.append(get_schema_renderer_method(empty=True, as_string=True)(event_type["schema"]))
        except LookupError:
            logger.exception("Missing Choice table in event_type %s", event_type["value"])

    return get_hash_from_queryset(queryset=queryset, request=request, extra_salt=":".join(schemas))


def build_event_type_etag_header(request, *args, **kwargs) -> str:
    queryset = EventType.objects.filter(id=kwargs["eventtype_id"])
    queryset = queryset.values(*EVENT_TYPE_FIELDS_FOR_ETAG)
    schema = None
    if event_type := queryset.first():
        schema = event_type["schema"]
        schema = get_schema_renderer_method(as_string=True)(schema)
    return get_hash_from_queryset(queryset=queryset, request=request, extra_salt=schema)


def get_most_recent_update_datetime_by_queryset(queryset: QuerySet) -> Optional[datetime]:
    if not queryset.exists():
        return None
    return queryset.order_by("-updated_at").last().updated_at


def concatenate_fields_from_model(model_fields: Iterable[str], model: Model) -> str:
    fields_set = filter(lambda field: getattr(model, field) is not None, model_fields)
    field_values = map(lambda field: str(getattr(model, field)), fields_set)
    return ":".join(field_values)


def build_etag_header(entry_to_string: Callable, queryset: QuerySet, salt: str = None) -> Optional[str]:
    if not queryset.exists():
        return hashlib.md5(datetime.min.isoformat().encode("utf-8")).hexdigest()

    concatenated_entries = ":".join(map(entry_to_string, queryset.all()))
    if salt is not None:
        concatenated_entries += str(salt)
    return hashlib.md5(concatenated_entries.encode("utf-8")).hexdigest()
