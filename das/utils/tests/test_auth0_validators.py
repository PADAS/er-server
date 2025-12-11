import json
from unittest.mock import MagicMock, patch

import pytest
from joserfc.errors import InvalidKeyIdError

from django.core.cache.backends.locmem import LocMemCache

from utils.auth0.auth0_validators import Auth0JWTBearerTokenValidator

mock_jwks_response = {
    "keys": [
        {
            "kty": "RSA",
            "use": "sig",
            "kid": "test-key-id",
            "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbIS",
            "e": "AQAB",
            "alg": "RS256",
        }
    ]
}


@pytest.fixture(autouse=True)
def mock_urlopen():
    """Mock urlopen to return JWKS response."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_jwks_response).encode("utf-8")
    with patch("utils.auth0.auth0_validators.urlopen", return_value=mock_response) as mock:
        yield mock


@pytest.fixture(autouse=True)
def in_memory_cache():
    """Mock the shared cache."""
    cache = LocMemCache("shared", {})
    with patch("utils.auth0.auth0_validators.caches", {"shared": cache}):
        yield cache
        cache.clear()


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock Django settings with relevant configuration."""
    with patch("utils.auth0.auth0_validators.settings") as mock_settings:
        mock_settings.AUTH0_RESOURCE_SERVER = "https://api.example.com"
        mock_settings.AUTH0_JWKS_CACHE_TTL_S = 3600
        mock_settings.SHARED_CACHE_ALIAS = "shared"
        yield mock_settings


@pytest.fixture
def validator_test_instance():
    """Test validator instance with hardcoded test domain."""
    return Auth0JWTBearerTokenValidator(auth0_custom_domain_provider=lambda: "test.auth0.com")


class TestAuth0JWTBearerTokenValidator:

    class TestInit:
        def test_init_sets_super_values(self, validator_test_instance, mock_settings):
            assert validator_test_instance.issuer == "https://test.auth0.com/"
            assert validator_test_instance.resource_server == mock_settings.AUTH0_RESOURCE_SERVER

        @pytest.mark.parametrize("resource_server", ["", "  "])
        def test_resource_server_empty_or_whitespace_raises_error(self, resource_server, mock_settings):
            mock_settings.AUTH0_RESOURCE_SERVER = resource_server

            with pytest.raises(ValueError, match="AUTH0_RESOURCE_SERVER must be configured"):
                Auth0JWTBearerTokenValidator(auth0_custom_domain_provider=lambda: "test.auth0.com")

    class TestCaching:
        def test_get_jwks_cache_hit(self, validator_test_instance, in_memory_cache, mock_urlopen):
            cached_jwks = {"keys": ["cached_key"]}

            in_memory_cache.set(validator_test_instance.cache_key, cached_jwks, 3600)

            jwks = validator_test_instance.get_jwks()

            assert jwks == cached_jwks
            mock_urlopen.assert_not_called()

        def test_get_jwks_cache_miss_fetches_from_url(self, validator_test_instance, mock_urlopen, in_memory_cache):
            jwks = validator_test_instance.get_jwks()

            assert jwks == mock_jwks_response
            mock_urlopen.assert_called_once_with("https://test.auth0.com/.well-known/jwks.json", timeout=10)
            assert in_memory_cache.get(validator_test_instance.cache_key) == mock_jwks_response

        def test_force_jwks_cache_refresh(self, validator_test_instance, mock_urlopen, in_memory_cache):
            validator_test_instance.force_jwks_cache_refresh()

            mock_urlopen.assert_called_once_with("https://test.auth0.com/.well-known/jwks.json", timeout=10)
            assert in_memory_cache.get(validator_test_instance.cache_key) == mock_jwks_response

        def test_force_jwks_cache_refresh_sets_ttl(self, validator_test_instance, mock_urlopen, mock_settings):
            mock_cache = MagicMock()
            with patch("utils.auth0.auth0_validators.caches", {"shared": mock_cache}):
                validator = Auth0JWTBearerTokenValidator(auth0_custom_domain_provider=lambda: "test.auth0.com")
                validator.force_jwks_cache_refresh()

                mock_cache.set.assert_called_once_with(validator.cache_key, mock_jwks_response, 3600)

    class TestTokenAuthentication:
        def test_authenticate_token_success(self, validator_test_instance):
            with patch.object(validator_test_instance.__class__.__bases__[0], "authenticate_token") as mock_super_auth:
                mock_claims = {"sub": "user123", "iss": "https://test.auth0.com/"}
                mock_super_auth.return_value = mock_claims

                result = validator_test_instance.authenticate_token("fake.jwt.token")

                assert result == mock_claims
                mock_super_auth.assert_called_once_with("fake.jwt.token")

        def test_authenticate_token_with_key_rotation(self, validator_test_instance, mock_urlopen):
            with patch.object(validator_test_instance.__class__.__bases__[0], "authenticate_token") as mock_super_auth:
                mock_claims = {"sub": "user123", "iss": "https://test.auth0.com/"}

                mock_super_auth.side_effect = [InvalidKeyIdError("Unknown key ID"), mock_claims]

                result = validator_test_instance.authenticate_token("fake.jwt.token")

                assert result == mock_claims
                assert mock_super_auth.call_count == 2
                mock_urlopen.assert_called_once_with("https://test.auth0.com/.well-known/jwks.json", timeout=10)

        def test_fetch_jwks_error_handling(self, validator_test_instance):
            with patch("utils.auth0.auth0_validators.urlopen", side_effect=Exception("Network error")):
                with pytest.raises(Exception, match="Network error"):
                    validator_test_instance._fetch_jwks()
