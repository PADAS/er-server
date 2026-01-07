import logging
from urllib.parse import urlsplit

from auth0.authentication import GetToken

from django.conf import settings

logger = logging.getLogger(__name__)


def get_auth0_management_api_access_token() -> str:
    """Get Auth0 management API access token for backend operations."""
    client_id = getattr(settings, "AUTH0_CLIENT_ID_FOR_MANAGEMENT_API")
    client_secret = getattr(settings, "AUTH0_CLIENT_SECRET_FOR_MANAGEMENT_API")

    get_token_endpoints = GetToken(get_auth0_custom_domain(), client_id, client_secret=client_secret)

    management_api_audience = f"https://{get_auth0_tenant_domain_for_management_api_only()}/api/v2/"
    management_api_token = get_token_endpoints.client_credentials(audience=management_api_audience)

    return management_api_token["access_token"]


def get_auth0_custom_domain() -> str:
    """
    Extract and validate the Auth0 custom domain from Django settings.

    Retrieves the AUTH0_CUSTOM_DOMAIN setting and parses it to return only the
    hostname portion. This ensures consistent domain formatting even if the
    configuration includes a protocol scheme or path.

    Returns:
        str: The hostname portion of the Auth0 custom domain

    Raises:
        ValueError: If AUTH0_CUSTOM_DOMAIN is not configured or is empty
    """

    return _get_auth0_domain("AUTH0_CUSTOM_DOMAIN")


def get_auth0_tenant_domain_for_management_api_only() -> str:
    """
    Extract and validate the Auth0 non-custom domain for Management API access.

    Retrieves the AUTH0_TENANT_DOMAIN setting and
    parses it to return only the hostname portion. This domain is specifically
    used for Auth0 Management API calls which require the non-custom domain.

    Returns:
        str: The hostname portion of the Auth0 non-custom domain

    Raises:
        ValueError: If AUTH0_TENANT_DOMAIN is not
                   configured or is empty
    """

    return _get_auth0_domain("AUTH0_TENANT_DOMAIN")


def _get_auth0_domain(settings_key: str) -> str:
    """
    Internal helper to extract and validate Auth0 domain settings.

    Retrieves the specified Auth0 domain setting from Django configuration and
    parses it using urlsplit to extract only the hostname portion. This handles
    cases where the domain might be misconfigured with protocols or paths.

    Args:
        settings_key (str): The Django setting key to retrieve (e.g.,
                           'AUTH0_CUSTOM_DOMAIN')

    Returns:
        str: The parsed hostname portion of the domain

    Raises:
        ValueError: If the specified setting is not configured or is empty
    """
    raw_value = getattr(settings, settings_key).strip()
    if not raw_value:
        raise ValueError(f"{settings_key} must be configured and non-empty in settings")

    parsed = urlsplit(raw_value, allow_fragments=False)
    hostname = parsed.hostname or parsed.path.rstrip("/")

    if hostname != raw_value:
        logger.warning("'%s' was changed to '%s'. Fix %s to be only the domain.", raw_value, hostname, settings_key)

    return hostname
