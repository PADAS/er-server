from urllib.parse import urlencode
from django.shortcuts import redirect


class DefaultFilterMixin:
    def get_default_filters(self, request):
        """Set default filters to the page.
            request (Request)
            Returns (dict):
                Default filter to encode.
        """
        raise NotImplementedError()

    def changelist_view(self, request, extra_context=None):
        ref = request.META.get('HTTP_REFERER', '')
        path = request.META.get('PATH_INFO', '')
        # If already have query parameters or if the page
        # was referred from it self (by drilldown or redirect)
        # don't apply default filter.
        if request.GET or ref.endswith(path):
            return super().changelist_view(
                request,
                extra_context=extra_context
            )
        query = urlencode(self.get_default_filters(request))
        return redirect('{}?{}'.format(path, query))
