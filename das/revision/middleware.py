from django.db.models import signals
from django.utils.functional import curry

from revision.manager import RevisionMixin


class RevisionMiddleware(object):
    def process_request(self, request):
        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            if hasattr(request, 'user') and request.user.is_authenticated():
                user = request.user
            else:
                user = None
            pre_save_info = curry(self._pre_save_info, user)

            signals.pre_save.connect(pre_save_info,
                                     dispatch_uid=(self.__class__, request,),
                                     weak=False)

    def process_response(self, request, response):
        signals.post_save.disconnect(dispatch_uid=(self.__class__, request,))
        return response

    def _pre_save_info(self, user, sender, instance, **kwargs):
        if issubclass(sender, RevisionMixin):
            setattr(instance, 'revision_user', user)