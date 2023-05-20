import hashlib
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any, Callable, Iterable, Optional

from django.contrib.auth.models import User
from django.contrib.gis.db.models import Model
from django.http import QueryDict

from activity.models import EventType, PatrolType
from activity.views.events.utils import EventTypeQuerysetMixin

PATROL_TYPE_FIELDS = ("value", "display", "ordernum", "icon", "is_active", "default_priority")
EVENT_TYPE_FIELDS = (
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


def build_event_types_etag_header(request, *args, **kwargs) -> datetime:
    event_type_to_string = partial(concatenate_fields_from_model, EVENT_TYPE_FIELDS)
    queryset_builder = EventTypeQueryset(request.user, request.GET)
    return build_etag_header(event_type_to_string, queryset_builder.get_queryset())


def build_event_type_etag_header(*args, **kwargs) -> str:
    event_type_to_string = partial(concatenate_fields_from_model, EVENT_TYPE_FIELDS)
    queryset = EventType.objects.filter(id=kwargs["eventtype_id"])
    return build_etag_header(event_type_to_string, queryset)


def build_event_type_last_modified_header(*args, **kwargs) -> datetime:
    queryset = EventType.objects.filter(id=kwargs["eventtype_id"])
    return get_most_recent_update_datetime_by_queryset(queryset)


def build_event_types_last_modified_header(request, *args, **kwargs) -> datetime:
    queryset_builder = EventTypeQueryset(request.user, request.GET)
    return get_most_recent_update_datetime_by_queryset(queryset_builder.get_queryset())


def get_most_recent_update_datetime_by_queryset(queryset: object) -> Optional[datetime]:
    if not queryset.exists():
        return None
    return queryset.order_by("-updated_at").last().updated_at


def concatenate_fields_from_model(model_fields: Iterable[str], model: Model) -> str:
    fields_set = filter(lambda field: getattr(model, field) is not None, model_fields)
    field_values = map(lambda field: str(getattr(model, field)), fields_set)
    return ":".join(field_values)


def build_etag_header(entry_to_string: Callable, queryset: object) -> Optional[str]:
    if not queryset.exists():
        return None

    concatenated_entries = ":".join(map(entry_to_string, queryset.all()))
    return hashlib.md5(concatenated_entries.encode("utf-8")).hexdigest()
