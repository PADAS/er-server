from accounts.views import UsersView
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
