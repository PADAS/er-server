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
