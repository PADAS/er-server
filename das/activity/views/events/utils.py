from django.db import models

from activity.models import Event, EventCategory, EventType
from utils.categories import (
    ACTIONS,
    GEO_ACTIONS,
    make_eventcategory_permission_codename,
)
from utils.json import parse_bool


class AllowedCategoriesMixin:
    def _get_allowed_categories_by_user(self, user):
        event_categories = EventCategory.get_category_keys()
        allowed_categories = [
            event_category
            for event_category in event_categories
            if self._is_event_category_visible_by_user(event_category, user)
        ]
        return allowed_categories

    def _is_event_category_visible_by_user(self, event_category, user):
        permission_names = self._build_permission_names(event_category)
        return any((user.has_perm(permission_name) for permission_name in permission_names))

    def _build_permission_names(self, event_category):
        action_permissions = [
            f"activity.{make_eventcategory_permission_codename(event_category, action)}" for action in ACTIONS
        ]
        geoaction_permissions = [
            f"activity.{make_eventcategory_permission_codename(event_category, action, True)}" for action in GEO_ACTIONS
        ]

        return action_permissions + geoaction_permissions


class EventTypeQuerysetMixin(AllowedCategoriesMixin):
    def get_queryset(self):
        user = self.request.user
        query_params = self.request.query_params
        category = query_params.get("category")
        include_inactive = parse_bool(query_params.get("include_inactive"))
        is_collection = query_params.get("is_collection")
        updated_since = query_params.get("updated_since", None)
        queryset = (
            EventType.objects.all_sort()
            .select_related("category")
            .annotate(in_use=models.Exists(Event.objects.filter(event_type=models.OuterRef("id"))))
        )

        if updated_since:
            queryset = queryset.filter(updated_at__gte=updated_since)

        if include_inactive:
            queryset = queryset.filter(category__is_active=True)
        else:
            queryset = queryset.filter(category__is_active=True, is_active=True)

        allowed_categories = self._get_allowed_categories_by_user(user)

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
