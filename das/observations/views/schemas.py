from das_server.views import CustomSchema


class InactiveSubjectsViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
            query_params = {
                "name": "include_inactive",
                "in": "query",
                "description": "Include inactive subjects in list.",
            }

            operation["parameters"].append(query_params)
        return operation


class SubjectsViewSchema(InactiveSubjectsViewSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
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
                    "description": """
                        This can be a comma-delimited list of subject group IDs or a single subject group ID.
                        The API will return all subjects that are members of any of the specified groups.
                        If the subject group ID is a UUID only, it will be treated as a subject group ID.
                    """,
                    "schema": {
                        "oneOf": [
                            {"type": "string", "format": "uuid", "description": "Single subject group UUID"},
                            {
                                "type": "string",
                                "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(,[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})*$",
                                "description": "Comma-separated list of UUIDs",
                            },
                        ],
                        "examples": [
                            "123e4567-e89b-12d3-a456-426614174000",
                            "123e4567-e89b-12d3-a456-426614174000,987e6543-e21b-54d3-a654-426614174999",
                        ],
                    },
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
                    "description": "Return Subjects that have been updated since the given timestamp.",
                },
                {
                    "name": "position_updated_since",
                    "in": "query",
                    "description": "Return Subjects that have had their position updated since the given timestamp.",
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
                {
                    "name": "subject_subtypes",
                    "in": "query",
                    "description": "List of subtype values comma-delimited for which Subjects should be listed.",
                    "schema": {"type": "string"},
                },
            ]

            operation["parameters"].extend(query_params)
        return operation


class SubjectGroupsViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
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
            operation["parameters"].extend(query_params)
        return operation
