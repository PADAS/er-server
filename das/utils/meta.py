from rest_framework.metadata import BaseMetadata


class NoMetaData(BaseMetadata):
    def determine_metadata(self, request, view):
        return None
