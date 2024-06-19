from django.contrib.auth.models import Permission
from django.db.models import Q

from accounts.models import PermissionSet, User
from activity.models import EventCategory
from utils.tenant.thread import get_tenant_settings

ACTIONS = ("create", "update", "read", "delete")
GEO_ACTIONS = ("view", "add", "change", "delete")
GEOGRAPHIC_DISTANCE = "gd"
GEOGRAPHIC_DISTANCE_SUFIX = "_gd"


def make_eventcategory_permission_codename(
    eventcategory_value: str, action: str, is_geographic=False, app_label=None
) -> str:
    """make an eventcategory based permission codename

    Args:
        eventcategory_value (str): EventCategory name
        action (str): the CRUD operation
        is_geographic (bool, optional): Is this a geographic distance permission. Defaults to False.
    Returns:
        (str): the codename
    """
    if is_geographic:
        return (
            f"{app_label}.{action}_{eventcategory_value}_gd"
            if app_label
            else f"{action}_{eventcategory_value}_{GEOGRAPHIC_DISTANCE}"
        )
    return f"{app_label}.{eventcategory_value}_{action}" if app_label else f"{eventcategory_value}_{action}"


def get_categories_and_geo_categories(user: User):
    results = {"categories": [], "geo_categories": []}
    events_categories = list(EventCategory.objects.values_list("value", flat=True))

    for event_category in events_categories:
        for action in ACTIONS:
            permission_name = make_eventcategory_permission_codename(event_category, action, app_label="activity")
            if user.has_perm(permission_name):
                results["categories"].append(event_category)

        for action in GEO_ACTIONS:
            geo_permission_name = make_eventcategory_permission_codename(
                event_category, action, True, app_label="activity"
            )
            if user.has_perm(geo_permission_name) and event_category not in results["categories"]:
                results["geo_categories"].append(event_category)
    return results


def should_apply_geographic_features(user: User) -> list:
    if user.is_anonymous or user.is_superuser:
        return []

    results = get_categories_and_geo_categories(user)
    return results["geo_categories"]


class EventCategoryRelatedPermissionSetActions:
    def __init__(self, event_category: EventCategory) -> None:
        self.event_category = event_category

    def is_event_category_permission_set_changed_by_user(self) -> bool:
        """
        Checks if the event category permission set has been changed by the user.

        Returns:
            bool: True if the permission set has been changed, False otherwise.
        """
        from accounts.utils import add_tenant_to_permission_codename

        default_permissions_number = 4
        tenant_settings = get_tenant_settings()
        actions_codenames = []
        geo_codenames = []

        for action in ACTIONS:
            codename = make_eventcategory_permission_codename(
                eventcategory_value=self.event_category.value, action=action
            )
            codename = add_tenant_to_permission_codename(tenant_id=tenant_settings.id, codename=codename)
            actions_codenames.append(codename)
        for action in GEO_ACTIONS:
            codename = make_eventcategory_permission_codename(
                eventcategory_value=self.event_category.value, action=action, is_geographic=True
            )
            codename = add_tenant_to_permission_codename(tenant_id=tenant_settings.id, codename=codename)
            geo_codenames.append(codename)

        base_qs = PermissionSet.objects.prefetch_related("permissions").all()

        try:
            permission_set = base_qs.get(name=self.event_category.auto_permissionset_name)
            geo_permission_set = base_qs.get(name=self.event_category.auto_geographic_permission_set_name)
        except PermissionSet.DoesNotExist:
            return True

        if (
            geo_permission_set.permissions.exclude(codename__in=geo_codenames).exists()
            or geo_permission_set.permissions.filter(codename__in=geo_codenames).count() != default_permissions_number
            or geo_permission_set.children.exists()
        ):
            was_changed = True

        elif (
            permission_set.permissions.exclude(codename__in=actions_codenames).exists()
            or permission_set.permissions.filter(codename__in=actions_codenames).count() != default_permissions_number
            or permission_set.children.exists()
        ):
            was_changed = True

        else:
            was_changed = False

        return was_changed

    def delete_permissions_sets_and_permissions_related_to_event_category(self) -> None:
        """
        Deletes the permission sets and permissions related to the event category.

        This method first sets the related permissions set, then retrieves the permission IDs
        associated with the event category. It deletes the permissions with those IDs and
        finally deletes the related permissions set.

        Returns:
            None
        """
        related_permissions_set = PermissionSet.objects.filter(
            Q(name=self.event_category.auto_geographic_permission_set_name)
            | Q(name=self.event_category.auto_permissionset_name)
        )

        permissions_ids_to_delete = (
            related_permissions_set.prefetch_related("permissions")
            .filter(permissions__codename__contains=self.event_category.value)
            .values_list("permissions__id", flat=True)
        )

        Permission.objects.filter(id__in=permissions_ids_to_delete).delete()
        related_permissions_set.delete()
