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
        return f"{item.get('first_name')} {item.get('last_name')}"


class SubjectsDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SubjectsView
    schema_title = "Subjects"
    schema_description = "Subjects list"
    default_title_field = "name"


class ChoicesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = ChoicesView
    schema_title = "Choices"
    schema_description = "All choices schema list"
    default_const_field = "id"
    default_title_field = "value"
    default_description_field = "display"


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
