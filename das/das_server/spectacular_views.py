from drf_spectacular.views import SpectacularSwaggerView

from django.urls import reverse


class SwaggerUIViewWithLogin(SpectacularSwaggerView):
    """Swagger UI with optional *Log in* link."""

    template_name = "drf_spectacular/swagger_ui_with_login.html"
    permission_classes: list = []  # allow any user to load the UI

    def get(self, request, *args, **kwargs):
        """Return swagger HTML with optional login_url context variable."""
        response = super().get(request, *args, **kwargs)
        if not request.user.is_authenticated:
            response.data["login_url"] = reverse("admin:login") + f"?next={request.path}"
        return response
