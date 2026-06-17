from __future__ import annotations

from activity.models import EventCategory
from utils.categories import (
    ACTIONS,
    GEO_ACTIONS,
    make_eventcategory_permission_codename,
)


def build_event_category_permission_names(event_category: str) -> list[str]:
    """Return the full set of permission names that grant visibility of an
    event category: the union of the general ACTIONS and the geographic
    GEO_ACTIONS codenames.

    This is the single source of truth shared by ``get_allowed_categories_by_user``,
    the ``/categories`` list and detail endpoints, and
    ``EventCategoryObjectPermissions``.
    """
    action_permissions = [
        f"activity.{make_eventcategory_permission_codename(event_category, action)}" for action in ACTIONS
    ]
    geoaction_permissions = [
        f"activity.{make_eventcategory_permission_codename(event_category, action, True)}" for action in GEO_ACTIONS
    ]

    return action_permissions + geoaction_permissions


def is_event_category_visible_by_user(event_category: str, user) -> bool:
    permission_names = build_event_category_permission_names(event_category)
    return any(user.has_perm(permission_name) for permission_name in permission_names)


def get_allowed_categories_by_user(user) -> list[str]:
    """Return the list of event category keys visible to ``user``.

    A category is visible when the user holds at least one general or
    geographic permission for it (union of general ACTIONS and geographic
    GEO_ACTIONS codenames), mirroring the logic of
    ``is_event_category_visible_by_user``.
    """
    return [
        event_category
        for event_category in EventCategory.get_category_keys()
        if is_event_category_visible_by_user(event_category, user)
    ]
