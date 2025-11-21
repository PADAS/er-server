import logging
from threading import local

from django.db.models import signals

from revision.manager import RevisionMixin

logger = logging.getLogger(__name__)
request_context = local()
request_context.user = None


def attach_revision_user_to_instance(sender, instance, **kwargs):
    logger.debug("attach_revision_user_to_instance called for %s instance %s", sender.__name__, instance.id)
    if issubclass(sender, RevisionMixin):
        setattr(instance, "revision_user", request_context.user)
        logger.debug("Setting revision user to '%s'", request_context.user)


class RevisionMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response
        signals.pre_save.connect(attach_revision_user_to_instance, weak=False)
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        self._process_request(request)

        response = self.get_response(request)

        response = self._process_response(request, response)
        # Code to be executed for each request/response after
        # the view is called.

        return response

    def _process_request(self, request):
        if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            if hasattr(request, "user") and request.user.is_authenticated:
                request_context.user = request.user
                logger.debug(
                    f"Setting thread request_context.user to '{request.user.username}' for request {request.path}"
                )
            else:
                request_context.user = None

    def _process_response(self, request, response):
        request_context.user = None
        logger.debug("Clear revision user in current thread")
        return response
