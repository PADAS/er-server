from das_server.views import CustomSchema


class InactiveSubjectsViewSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = {
                "name": "include_inactive",
                "in": "query",
                "description": "Include inactive subjects in list.",
            }
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].append(query_params)
        return operation


class SubjectsViewSchema(InactiveSubjectsViewSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {"name": "tracks_since", "in": "query", "description": "Include tracks since this timestamp"},
                {
                    "name": "tracks_until",
                    "in": "query",
                    "description": "Include tracks up through this timestamp",
                },
                {
                    "name": "bbox",
                    "in": "query",
                    "description": "Include subjects having track data within this bounding box defined by a 4-tuple of coordinates marking west, south, east, north.",
                },
                {
                    "name": "subject_group",
                    "in": "query",
                    "description": "Indicate a subject group for which Subjects should be listed.",
                },
                {
                    "name": "subject_group",
                    "in": "query",
                    "description": "Indicate a subject group for which Subjects should be listed.",
                    "schema": {"type": "UUID"},
                },
                {
                    "name": "name",
                    "in": "query",
                    "description": "Find subjects with the given name.",
                    "schema": {"type": "UUID"},
                },
                {
                    "name": "updated_since",
                    "in": "query",
                    "description": "Return Subject that have been updated since the given timestamp.",
                },
                {
                    "name": "render_last_location",
                    "in": "query",
                    "description": "Indicate whether to render each subject's last location.",
                },
                {
                    "name": "tracks",
                    "in": "query",
                    "description": "Indicate whether to render each subject's recent tracks.",
                },
                {"name": "id", "in": "query", "description": "A comma-delimited list of Subject IDs."},
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class SubjectGroupsViewSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "include_hidden",
                    "in": "query",
                    "description": "If true, return all subject groups including hidden groups. Default is false.",
                },
                {
                    "name": "isvisible",
                    "in": "query",
                    "description": "Return only visible groups by default. If isvisible=false then return only hidden groups. see include_hidden",
                },
                {
                    "name": "include_inactive",
                    "in": "query",
                    "description": "Include inactive subjects in subject group list.",
                },
                {
                    "name": "flat",
                    "in": "query",
                    "description": "flatten the list of groups returned, no nested parent/child",
                },
                {"name": "group_name", "in": "query", "description": "find subject groups with this name"},
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation
