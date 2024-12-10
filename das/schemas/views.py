from accounts.views import UsersView
from mapping.views import FeatureSetListJsonView
from observations.views import SubjectsView
from schemas.view_mixins import DynamicSchemaFromSourceView


class FeatureCategoriesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = FeatureSetListJsonView
    data_path = "features"

    schema_title = "FeatureCategories"
    schema_description = "A list of all feature categories available to the client"
    default_title_field = "name"
    default_description_field = "description"


class UsersDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = UsersView
    schema_title = "Users"
    schema_description = "A list of all users available to the client"
    default_title_field = "display_name"

    def get_display_name_from_item(self, obj):
        return f"{obj['first_name']} {obj['last_name']}"

    def get_requested_fields(self, request):
        fields = super().get_requested_fields(request)
        if "display_name" in fields:
            fields.remove("display_name")
            fields.append("first_name")
            fields.append("last_name")
        return fields


class SubjectsDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SubjectsView
    schema_title = "Subjects"
    schema_description = "A list of all subjects available to the client"
    default_title_field = "name"
