from observations.views import InactiveSubjectsViewSchema


class GearsViewSchema(InactiveSubjectsViewSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
            query_params = [
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
                {"name": "id", "in": "query", "description": "A comma-delimited list of Subject IDs."},
            ]

            operation["parameters"].extend(query_params)
        return operation
