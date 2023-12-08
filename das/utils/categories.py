from accounts.models import User
from activity.models import EventCategory

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
