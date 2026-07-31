"""RFC 9728 OAuth 2.0 Protected Resource Metadata.

Serves ``/.well-known/oauth-protected-resource`` so interactive clients can
discover which authorization server(s) a site accepts before they hold a token.
This replaces the ad-hoc discovery role that ``/api/v1.0/status`` used to serve.

The endpoint is deliberately a plain Django view rather than a DRF view: it must
answer unauthenticated, pre-token probes, whereas DRF defaults every view to
``IsAuthenticated`` with Auth0 JWT authentication running first.
"""

from __future__ import annotations

from oauth2_provider.models import get_application_model
from oauth2_provider.settings import oauth2_settings

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import cache_control

from utils.auth0.helpers import get_auth0_custom_domain
from utils.tenant import get_tenant_settings

Application = get_application_model()

PROTECTED_RESOURCE_URL_NAME = "oauth-protected-resource"
CACHE_MAX_AGE_SECONDS = 300


@cache_control(public=True, max_age=CACHE_MAX_AGE_SECONDS)
def oauth_protected_resource(request: HttpRequest) -> JsonResponse:
    """Return this site's RFC 9728 protected-resource metadata.

    ``authorization_servers`` is computed from the site's migration state:

    * legacy site (``require_idp = False``) -> DAS-as-authorization-server only;
    * migrated site with any ``bypass_auth0 = True`` application -> Auth0 tenant
      plus DAS-as-authorization-server;
    * migrated site with no bypassed applications -> Auth0 tenant only (end state).
    """
    tenant = get_tenant_settings()
    das_authorization_server = oauth2_settings.oidc_issuer(request)

    if not tenant.feature_flags.require_idp:
        authorization_servers = [das_authorization_server]
    else:
        auth0_authorization_server = f"https://{get_auth0_custom_domain()}/"
        if Application.objects.filter(bypass_auth0=True).exists():
            authorization_servers = [auth0_authorization_server, das_authorization_server]
        else:
            authorization_servers = [auth0_authorization_server]

    # RFC 9728 s3.3: the resource identifier must be the one the metadata URL was
    # built from, i.e. this request's own origin. A client rebuilds it from the URL
    # it fetched and discards the document if it does not match.
    resource = request.build_absolute_uri("/").rstrip("/")

    return JsonResponse(
        {
            "resource": resource,
            "authorization_servers": authorization_servers,
        }
    )
