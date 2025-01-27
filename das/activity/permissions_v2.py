from rest_framework.permissions import IsAuthenticated


class GenericEventCategoryPermission(IsAuthenticated):
    """
    Permission class for EventCategory dependant objects.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Map of view actions to permission verbs.
        # This map is used to determine the permission verb needed to perform an action.
        # The permission verb is used to build the permission codename.
        # Verbs are kind of levels of access, e.g. read, create, update, delete...

        self.view_actions_map = {
            "list": "read",
            "retrieve": "read",
            "create": "create",
            "update": "update",
            "destroy": "delete",
        }

    def has_permission(self, request, view):
        # These methods are allowed for everyone
        if request.method in ["OPTIONS", "HEAD"]:
            return super().has_permission(request, view)

        # Must be authenticated (because we extend IsAuthenticated).
        if not super().has_permission(request, view):
            return False

        permission_verb = self.view_actions_map.get(view.action)
        if not permission_verb:
            # If the action is not in the map trigger an error for developers, the action must be added to the map.
            raise ValueError(f"Action {view.action} not in view_actions_map")

    def get_category_value(self, obj):
        """
        Must be implemented by subclasses; returns the string used in the permission codename.
        e.g. for EventType objects: obj.category.value
             for EventCategory objects: obj.value
        """
        raise NotImplementedError()


class EventCategoryPermission(GenericEventCategoryPermission):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.view_actions_map.update(
            {
                "list_schemas": "read",
                "retrieve_schema": "read",
            }
        )

    def get_category_value(self, obj):
        return obj.value
