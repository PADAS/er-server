from __future__ import annotations

from django.db import models

from activity.category_permissions import (
    build_event_category_permission_names,
    get_allowed_categories_by_user,
    is_event_category_visible_by_user,
)
from activity.models import Event, EventType
from utils.json import parse_bool

__all__ = [
    "build_event_category_permission_names",
    "get_allowed_categories_by_user",
    "is_event_category_visible_by_user",
    "EventTypeQuerysetMixin",
]


class EventTypeQuerysetMixin:
    def get_queryset(self):
        user = self.request.user
        query_params = self.request.query_params
        category = query_params.get("category")
        include_inactive = parse_bool(query_params.get("include_inactive"))
        is_collection = query_params.get("is_collection")
        updated_since = query_params.get("updated_since", None)
        queryset = (
            EventType.objects.all_sort()
            .filter(version=EventType.VersionChoices.VERSION_1)
            .select_related("category")
            .annotate(in_use=models.Exists(Event.objects.filter(event_type=models.OuterRef("id"))))
        )

        if updated_since:
            queryset = queryset.filter(updated_at__gte=updated_since)

        if include_inactive:
            queryset = queryset.filter(category__is_active=True)
        else:
            queryset = queryset.filter(category__is_active=True, is_active=True)

        allowed_categories = get_allowed_categories_by_user(user)

        if category:
            if category not in allowed_categories:
                return queryset.none()
            queryset = queryset.by_category(category)
        else:
            if allowed_categories:
                queryset = queryset.by_category(allowed_categories)
            elif not is_collection:
                return queryset.none()

        if is_collection:
            queryset = queryset.by_is_collection(parse_bool(is_collection))

        return queryset
