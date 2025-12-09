import logging
from threading import local

from django.db.models import signals

from revision.manager import RevisionMixin

logger = logging.getLogger(__name__)
request_context = local()
request_context.request = None


def attach_revision_user_to_instance(sender, instance, **kwargs):
    if issubclass(sender, RevisionMixin):
        # Access request.user lazily - this happens during model save,
        # after DRF authentication has run, so request.user is correctly set
        user = None
        if request := getattr(request_context, "request", None):
            if _user := getattr(request, "user", None):
                if _user.is_authenticated:
                    user = _user
                    logger.debug("Setting revision user from request.user: '%s'", user.username)

        setattr(instance, "revision_user", user)


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
            # Store request object - user will be accessed lazily during model save
            # This ensures we get the user AFTER DRF authentication has run
            # (important when Bearer tokens are used instead of session auth)
            request_context.request = request
        else:
            request_context.request = None

    def _process_response(self, request, response):
        request_context.request = None
        logger.debug("Clear revision request in current thread")
        return response
