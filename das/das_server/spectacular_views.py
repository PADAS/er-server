"""
Custom DRF Spectacular views with authentication handling.
"""

from drf_spectacular.views import SpectacularRedocView, SpectacularSwaggerView

from django.http import HttpResponseRedirect
from django.urls import reverse


class AuthenticatedSpectacularSwaggerView(SpectacularSwaggerView):
    """
    Swagger UI view that redirects unauthenticated users to login page.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Redirect to DRF's login page with next parameter
            login_url = reverse("rest_framework:login")
            next_url = request.get_full_path()
            return HttpResponseRedirect(f"{login_url}?next={next_url}")
        return super().dispatch(request, *args, **kwargs)


class AuthenticatedSpectacularRedocView(SpectacularRedocView):
    """
    Redoc view that redirects unauthenticated users to login page.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Redirect to DRF's login page with next parameter
            login_url = reverse("rest_framework:login")
            next_url = request.get_full_path()
            return HttpResponseRedirect(f"{login_url}?next={next_url}")
        return super().dispatch(request, *args, **kwargs)
