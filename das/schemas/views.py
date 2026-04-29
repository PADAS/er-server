from __future__ import annotations

from typing import Any, Type

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from accounts.views import UsersView
from activity.views.types_v2 import EventTypesViewSet
from choices.views import ChoicesView
from mapping.spatialviews import SpatialFeatureListView
from observations.views import SourcesView, SubjectsView
from schemas.view_mixins import DynamicSchemaDataMixin, DynamicSchemaFromSourceView


class UsersDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = UsersView
    schema_title = "Users"
    schema_description = "All users list"
    default_title_field = "display_name"
    default_description_field = "username"

    def get_display_name_from_item(self, item: dict[str, Any]) -> str:
        display_name = f"{item.get('first_name')} {item.get('last_name')}".strip()
        return display_name or item.get("username") or item.get("email") or ""


class SourcesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SourcesView
    schema_title = "Sources"
    schema_description = "All data sources list"
    default_const_field = "id"
    default_title_field = "source_schema_title"
    default_description_field = "source_schema_description"

    def get_source_view(self, request: Request) -> Type[APIView]:
        class PermissionsFreeSourcesView(SourcesView, DynamicSchemaDataMixin):
            permission_classes = [IsAuthenticated]

        return PermissionsFreeSourcesView

    @staticmethod
    def _stripped_manufacturer_and_model(item: dict[str, Any]) -> tuple[str, str]:
        manufacturer_id = (item.get("manufacturer_id") or "").strip()
        model_name = (item.get("model_name") or "").strip()
        return manufacturer_id, model_name

    def get_source_schema_title_from_item(self, item: dict[str, Any]) -> str:
        manufacturer_id, model_name = self._stripped_manufacturer_and_model(item)
        if manufacturer_id and model_name:
            return model_name
        if manufacturer_id:
            return manufacturer_id
        if model_name:
            return model_name
        return item.get("source_type") or f"Source {item.get('id', '')}"

    def get_source_schema_description_from_item(self, item: dict[str, Any]) -> str | None:
        manufacturer_id, model_name = self._stripped_manufacturer_and_model(item)
        if manufacturer_id and model_name:
            return manufacturer_id
        return None


class SubjectsDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SubjectsView
    schema_title = "Subjects"
    schema_description = "Subjects list"
    default_title_field = "name"
    default_description_field = "subject_subtype"


class ChoicesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = ChoicesView
    schema_title = "Choices"
    schema_description = "All choices schema list"
    default_const_field = "value"
    default_title_field = "display"
    default_description_field = "field"

    def get_source_view(self, request: Request) -> Type[APIView]:
        class PermissionsFreeChoicesView(ChoicesView, DynamicSchemaDataMixin):
            permission_classes = [IsAuthenticated]

        return PermissionsFreeChoicesView


class SpatialFeaturesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SpatialFeatureListView
    schema_title = "Spatial Features"
    schema_description = "All spatial features list"
    default_title_field = "name"
    default_description_field = "feature_class_name"


class EventTypesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = EventTypesViewSet
    schema_title = "Event Types"
    schema_description = "All event types list"
    default_const_field = "id"
    default_title_field = "display"
    default_description_field = "value"
