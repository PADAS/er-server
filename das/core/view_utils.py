from core.tasks import delete_object
from utils.json import parse_bool


class AsyncDeleteObjectMixin:
    """Mixin for asynchronously deleting an object. It overrides the delete method found in the DestroyAPIView class.
    Requires the object to have a content type.

    Looks for a qparam of "async" in the request to determine if the object should be deleted asynchronously.
    If the object is deleted asynchronously, it will return a 204 status code with the task id and the location of the status endpoint.
    """

    def delete(self, request, *args, **kwargs):
        if not parse_bool(request.query_params.get("async", False)):
            return super().delete(request, *args, **kwargs)

        obj = self.get_object()
        response = delete_object(obj)
        return response
