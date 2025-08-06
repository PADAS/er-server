from typing import Type

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from accounts.views import UsersView
from activity.views.types_v2 import EventTypesViewSet
from choices.views import ChoicesView
from mapping.spatialviews import SpatialFeatureListView
from observations.views import SubjectsView
from schemas.view_mixins import DynamicSchemaFromSourceView


class UsersDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = UsersView
    schema_title = "Users"
    schema_description = "All users list"
    default_title_field = "display_name"

    def get_display_name_from_item(self, item: dict) -> str:
        display_name = f"{item.get('first_name')} {item.get('last_name')}".strip()
        return display_name or item.get("username") or item.get("email")


class SubjectsDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SubjectsView
    schema_title = "Subjects"
    schema_description = "Subjects list"
    default_title_field = "name"
    default_description_field = "subject_subtype"


class ChoicesDynamicSchemaView(DynamicSchemaFromSourceView):
    schema_title = "Choices"
    schema_description = "All choices schema list"
    default_const_field = "id"
    default_title_field = "value"
    default_description_field = "display"

    def get_source_view(self, request: Request) -> Type[APIView]:
        class PermissionsFreeChoicesView(ChoicesView):
            permission_classes = [IsAuthenticated]

        return PermissionsFreeChoicesView


class SpatialFeaturesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SpatialFeatureListView
    schema_title = "Spatial Features"
    schema_description = "All spatial features list"
    default_title_field = "properties.name"
    default_description_field = "properties.feature_type_name"
    data_path = "features"


class EventTypesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = EventTypesViewSet
    schema_title = "Event Types"
    schema_description = "All event types list"
    default_const_field = "id"
    default_title_field = "value"
    default_description_field = "display"
