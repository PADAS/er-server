from accounts.models import User
from activity.models import EventCategory


def get_categories_and_geo_categories(user: User):
    results = {"categories": [], "geo_categories": []}
    events_categories = list(
        EventCategory.objects.values_list("value", flat=True))

    for event_category in events_categories:
        for action in ["read", "create", "update", "delete"]:
            permission_name = f"activity.{event_category}_{action}"
            if user.has_perm(permission_name):
                results["categories"].append(event_category)

        for action in ["view", "add", "change", "delete"]:
            geo_permission_name = (
                f"activity.{action}_{event_category}_geographic_distance"
            )
            if (
                    user.has_perm(geo_permission_name)
                    and event_category not in results["categories"]
            ):
                results["geo_categories"].append(event_category)
    return results


def should_apply_geographic_features(user: User) -> list:
    if user.is_anonymous or user.is_superuser:
        return []

    results = get_categories_and_geo_categories(user)
    return results["geo_categories"]
