import json
import logging
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from authlib.oauth2.rfc9068 import JWTBearerTokenValidator
from authlib.oauth2.rfc9068.claims import JWTAccessTokenClaims
from joserfc.errors import InvalidKeyIdError

from django.conf import settings
from django.core.cache import caches

logger = logging.getLogger(__name__)


class Auth0JWTBearerTokenValidator(JWTBearerTokenValidator):
    """JWT Bearer Token Validator for Auth0.

    This class extends Authlib's RFC 9068 JWTBearerTokenValidator to provide
    Auth0-specific JWT access token validation. It validates tokens against
    the configured issuer and audience. It automatically fetches (and caches) the
    JSON Web Key Set (JWKS) from Auth0's well-known endpoint.

    The validator ensures that:
    - Tokens are properly signed by Auth0 using keys from the JWKS endpoint
    - The issuer (iss) claim matches the Auth0 domain
    - The audience (aud) claim matches the configured resource server
    - Standard JWT claims (exp, etc.) are valid
    """

    def __init__(self):
        auth0_domain = getattr(settings, "AUTH0_CUSTOM_DOMAIN").strip()
        if not auth0_domain:
            raise ValueError("AUTH0_CUSTOM_DOMAIN must be configured in settings")

        parsed = urlsplit(auth0_domain, allow_fragments=False)
        hostname = parsed.hostname or parsed.path.rstrip("/")
        issuer = f"https://{hostname}/"
        self.cache_key = f"auth0_jwks_{hash(issuer)}"
        self.jwks_url = urljoin(issuer, ".well-known/jwks.json")

        resource_server = getattr(settings, "AUTH0_RESOURCE_SERVER").strip()
        if not resource_server:
            raise ValueError("AUTH0_RESOURCE_SERVER must be configured in settings")

        self.jwks_cache_ttl_s = getattr(settings, "AUTH0_JWKS_CACHE_TTL_S")
        self.shared_cache_alias = getattr(settings, "SHARED_CACHE_ALIAS")

        super(Auth0JWTBearerTokenValidator, self).__init__(issuer=issuer, resource_server=resource_server)

    def _fetch_jwks(self) -> dict:
        try:
            jsonurl = urlopen(self.jwks_url, timeout=10)
            return json.loads(jsonurl.read().decode("utf-8"))
        except Exception as e:
            logger.error("Failed to fetch JWKS from %s: %s", self.jwks_url, e)
            raise

    def force_jwks_cache_refresh(self) -> None:
        shared_cache = caches[self.shared_cache_alias]
        jwks = self._fetch_jwks()
        shared_cache.set(self.cache_key, jwks, self.jwks_cache_ttl_s)

    def get_jwks(self) -> dict:
        shared_cache = caches[self.shared_cache_alias]
        return shared_cache.get_or_set(self.cache_key, self._fetch_jwks, self.jwks_cache_ttl_s)

    def authenticate_token(self, token_string: str) -> JWTAccessTokenClaims:
        try:
            return super().authenticate_token(token_string)
        except InvalidKeyIdError as e:
            logger.info("JWT signature validation failed, attempting JWKS refresh: %s", e)

            self.force_jwks_cache_refresh()
            return super().authenticate_token(token_string)
