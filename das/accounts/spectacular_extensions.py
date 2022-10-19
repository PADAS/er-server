"""
DRF Spectacular extensions for authentication classes.

This module provides OpenAPI documentation extensions for custom authentication
classes to resolve "could not resolve authenticator" warnings.
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class NoLoginOAuth2AuthenticationExtension(OpenApiAuthenticationExtension):
    """OpenAPI extension for NoLoginOAuth2Authentication."""

    target_class = "accounts.backends.NoLoginOAuth2Authentication"
    name = "NoLoginOAuth2"

    def get_security_definition(self, auto_schema):
        return {
            "type": "oauth2",
            "flows": {
                "clientCredentials": {
                    "tokenUrl": "/oauth2/token/",
                    "scopes": {"read": "Read access", "write": "Write access"},
                }
            },
        }


class BearerTokenInUrlAuthenticationExtension(OpenApiAuthenticationExtension):
    """OpenAPI extension for BearerTokenInUrlAuthentication."""

    target_class = "utils.authentication.BearerTokenInUrlAuthentication"
    name = "BearerTokenInUrl"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer"}


class SuperUserSessionAuthenticationExtension(OpenApiAuthenticationExtension):
    """OpenAPI extension for SuperUserSessionAuthentication."""

    target_class = "utils.authentication.SuperUserSessionAuthentication"
    name = "SuperUserSession"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid"}
