from accounts.views import UsersView
from choices.views import ChoicesView
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
    default_title_field = "display"
    default_description_field = "model"
    default_x_fields = {"field": "field", "ordernum": "ordernum", "icon": "icon", "value": "value"}
    default_const_field = "id"
    default_const_value = "id"
