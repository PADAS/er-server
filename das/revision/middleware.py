from functools import partial

from django.db.models import signals

from revision.manager import RevisionMixin


class RevisionMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response
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
        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            if hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
            else:
                user = None
            pre_save_info = partial(self._pre_save_info, user)

            signals.pre_save.connect(
                pre_save_info,
                dispatch_uid=(self.__class__, request,),
                weak=False,
            )

    def _process_response(self, request, response):
        signals.pre_save.disconnect(dispatch_uid=(self.__class__, request,))
        return response

    def _pre_save_info(self, user, sender, instance, **kwargs):
        if issubclass(sender, RevisionMixin):
            setattr(instance, 'revision_user', user)
