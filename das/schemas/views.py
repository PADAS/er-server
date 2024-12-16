from typing import List

from rest_framework.request import Request

from accounts.views import UsersView
from mapping.views import FeatureSetListJsonView
from observations.views import SubjectsView
from schemas.view_mixins import DynamicSchemaFromSourceView


class FeatureCategoriesDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = FeatureSetListJsonView
    data_path = "features"

    schema_title = "FeatureCategories"
    schema_description = "Feature categories list"
    default_title_field = "name"


class UsersDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = UsersView
    schema_title = "Users"
    schema_description = "All users list"
    default_title_field = "display_name"

    def get_display_name_from_item(self, item: dict) -> str:
        return f"{item.get('first_name')} {item.get('last_name')}"

    def get_requested_fields(self, request: Request) -> List[str]:
        fields_base = super().get_requested_fields(request)
        fields_map = {
            "display_name": ["first_name", "last_name"],
        }
        fields = []
        for field in fields_base:
            if field in fields_map:
                fields.extend(fields_map[field])
            else:
                fields.append(field)
        return fields


class SubjectsDynamicSchemaView(DynamicSchemaFromSourceView):
    source_view = SubjectsView
    schema_title = "Subjects"
    schema_description = "Subjects list"
    default_title_field = "name"
