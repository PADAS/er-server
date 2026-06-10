from __future__ import annotations

import logging
import uuid
from typing import Final, NamedTuple

from authlib.oauth2 import ResourceProtector
from authlib.oauth2.rfc6749 import OAuth2Token
from authlib.oauth2.rfc9068.claims import JWTAccessTokenClaims
from oauth2_provider.backends import OAuth2Backend
from oauth2_provider.contrib.rest_framework.authentication import OAuth2Authentication
from oauth2_provider.models import get_access_token_model

from django.contrib.auth.backends import BaseBackend, ModelBackend
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import APIException, AuthenticationFailed

from accounts.models import User
from accounts.utils import filter_permissions_by_tenant, parse_permission_codename
from utils.auth0.auth0_validators import Auth0JWTBearerTokenValidator
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException

logger = logging.getLogger("django.request")
act_as_logger = logging.getLogger("accounts.act_as")

AccessToken = get_access_token_model()


def _act_as_user_in_request(user, request):
    profile_header = request.META.get("HTTP_USER_PROFILE", None)
    if profile_header and user and not user.is_anonymous:
        logged_in_user = user
        profile_pk = uuid.UUID(profile_header)
        if profile_pk == logged_in_user.pk:
            logger.debug("User Profile %s is the same as logged in user %s", profile_pk, logged_in_user.pk)
            return user

        if 1 != logged_in_user.act_as_profiles.all().filter(pk=profile_pk).count():
            message = "act_as denied: profile %s not in act_as_profiles for user %s" % (profile_pk, logged_in_user.pk)
            act_as_logger.warning(
                message,
                extra={
                    "act_as_user": str(profile_pk),
                    "authenticated_user": str(logged_in_user.pk),
                    "reason": "not_in_act_as_profiles",
                },
            )
            raise exceptions.PermissionDenied(message)

        profile_user = User.objects.get(pk=profile_pk)
        if profile_user.is_staff or profile_user.is_superuser:
            message = "act_as denied: profile %s is staff or superuser" % (profile_user.pk,)
            act_as_logger.warning(
                message,
                extra={
                    "act_as_user": str(profile_user.pk),
                    "authenticated_user": str(logged_in_user.pk),
                    "reason": "privileged_target",
                },
            )
            raise exceptions.PermissionDenied(message)

        act_as_logger.info(
            "act_as: user %s is acting as user %s",
            logged_in_user.pk,
            profile_user.pk,
            extra={
                "act_as_user": str(profile_user.pk),
                "authenticated_user": str(logged_in_user.pk),
                "reason": "success",
            },
        )
        user = profile_user
    return user


class NoLoginOAuth2Backend(OAuth2Backend):
    """
    Disable user from logging in if they have is_nologin set on their account
    """

    def authenticate(self, request=None, **credentials):
        user = super().authenticate(request, **credentials)
        if not user:
            return user

        if user.is_nologin:
            logger.info("User %s tried to login with NoLogin set.", user.pk)
            return None

        if not request:
            return user

        return _act_as_user_in_request(user, request)


class NoLoginOAuth2Authentication(OAuth2Authentication):
    """
    Disable user from logging in if they have is_nologin set on their account
    Support for DRF
    """

    def authenticate(self, request):
        """
        Returns two-tuple of (user, token) if authentication succeeds,
        or None otherwise.
        """

        result = super().authenticate(request)
        if not result:
            # Check if there's an OAuth2 error (e.g., expired token)
            oauth2_error = getattr(request, "oauth2_error", {})
            if oauth2_error:
                # If there's an OAuth2 error, raise AuthenticationFailed to get 401
                raise exceptions.AuthenticationFailed("Token is invalid or expired")
            return None
        user = result[0]
        if user.is_nologin:
            logger.info("User %s tried to login with NoLogin set.", user.pk)
            raise exceptions.PermissionDenied()

        user = _act_as_user_in_request(user, request)
        return user, result[1]


class PriorityOAuth2SessionAuthentication(SessionAuthentication):
    """
    Authentication class that prioritizes OAuth2 tokens over session cookies.
    This ensures that when both a valid OAuth2 token and session cookie exist,
    the OAuth2 token takes precedence.
    """

    keyword = "Bearer"
    oauth2_auth = NoLoginOAuth2Authentication()

    def enforce_csrf(self, request):
        """
        CSRF enforcement logic for mixed authentication.

        CSRF protection is only needed for cookie-based authentication (sessions).
        Bearer tokens in headers are NOT vulnerable to CSRF attacks, so we skip
        CSRF validation when a Bearer token is present.

        We skip CSRF enforcement when:
        1. A Bearer/OAuth2 token is present (not vulnerable to CSRF)
        2. Session-only auth with a valid Django session (for admin->EULA flow)

        We enforce CSRF only when:
        - No authentication credentials present at all
        """
        # Check if there's a Bearer token in the Authorization header

        has_bearer_token = self._has_bearer_token(request)

        # If there's a Bearer token, skip CSRF validation
        # Bearer tokens are not vulnerable to CSRF attacks
        if has_bearer_token:
            return

        # If no Bearer token, check if we have a Django session with an authenticated user
        # This handles the admin login -> EULA redirect -> API call scenario
        # We avoid calling request.user to prevent recursion during authentication
        if hasattr(request, "session") and request.session and "_auth_user_id" in request.session:
            return

        # Default case: enforce CSRF for requests with no auth credentials
        return super().enforce_csrf(request)

    def authenticate_header(self, request):
        return self.keyword

    def _has_bearer_token(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        return auth_header.startswith(self.keyword + " ")

    def authenticate(self, request):
        # First, try OAuth2 token authentication
        has_bearer_token = self._has_bearer_token(request)

        oauth2_result = self.oauth2_auth.authenticate(request)

        if oauth2_result:
            return oauth2_result

        # Check if there was an OAuth2 error (e.g., expired token)
        oauth2_error = getattr(request, "oauth2_error", {})
        if oauth2_error and has_bearer_token:
            # If there's an OAuth2 error and we have a Bearer token, raise AuthenticationFailed
            raise exceptions.AuthenticationFailed("Token is invalid or expired")

        # If a Bearer token was provided but OAuth2 authentication didn't succeed,
        # do NOT fall back to session authentication. This ensures Bearer tokens
        # take absolute priority over session cookies.
        if has_bearer_token:
            # Bearer token was provided but authentication failed
            # Don't fall back to session, return None to try next auth class
            return None

        # Fall back to session authentication only if no Bearer token was provided
        # Handle both DRF request objects and Django WSGIRequest objects
        if hasattr(request, "_request"):
            # This is a DRF request object, use parent's authenticate method
            session_result = super().authenticate(request)
            return session_result
        else:
            # This is a Django WSGIRequest object, check for session user directly
            # see super().authenticate(request) for more details
            user = getattr(request, "user", None)
            if not user or not user.is_authenticated or not user.is_active:
                return None

            self.enforce_csrf(request)

            return (user, None)


class AccountsModelBackend(ModelBackend):
    """
    Handle hierarchical groups and obj permissions.

    Inspired by Django-Guardian
    """

    def get_user(self, user_id):
        return super().get_user(user_id)

    def get_user_permissions(self, user_obj, obj=None):
        """
        Returns a set of permission strings the user `user_obj` has from their
        `user_permissions`.
        """
        return set(("accounts.view_user",))

    def get_group_permissions(self, user_obj, obj=None):
        """
        Returns a set of permission strings that this user has through his/her
        groups and their children.
        """
        perms = set()
        if not user_obj.is_active or user_obj.is_anonymous:
            return perms

        can_cache = user_obj.is_superuser or not (obj and hasattr(obj, "get_obj_permission_set_ids"))
        if not can_cache or not hasattr(user_obj, "_group_perm_cache"):
            if user_obj.is_superuser:
                queryset = filter_permissions_by_tenant(
                    tenant_settings=get_tenant_settings(), queryset=Permission.objects.all()
                )
            else:
                user_ps_ids = user_obj.get_all_permission_sets(only_ids=True)
                try:
                    tenant_settings = get_tenant_settings()
                except TenantNotFoundInLocalThreadException:
                    logger.warning(
                        "get_group_permissions called with no current tenant set for user %s; returning empty permissions",
                        user_obj.pk,
                    )
                    return perms
                if obj and hasattr(obj, "get_obj_permission_set_ids"):
                    obj_ps_ids = obj.get_obj_permission_set_ids()
                    intersect_ids = user_ps_ids & obj_ps_ids

                    queryset = Permission.objects.filter(
                        permissionsetpermission__permissionset__in=intersect_ids,
                        permissionsetpermission__das_tenant_id=tenant_settings.id,
                    )
                else:
                    queryset = Permission.objects.filter(
                        permissionsetpermission__permissionset__in=user_ps_ids,
                        permissionsetpermission__das_tenant_id=tenant_settings.id,
                    )

            perm_values = queryset.values_list("content_type__app_label", "codename").order_by()
            for ct, codename in perm_values:
                tenant_id, codename = parse_permission_codename(codename)
                perms.add(f"{ct}.{codename}")
            if not can_cache:
                return perms
            user_obj._group_perm_cache = perms
        return user_obj._group_perm_cache

    def get_all_permissions(self, user_obj, obj=None):
        """
        Returns a set of permission strings that the given ``user_obj`` has for ``obj``
        """
        if not user_obj.is_active or user_obj.is_anonymous:
            return set()
        perms = self.get_group_permissions(user_obj, obj)
        perms.update(self.get_user_permissions(user_obj, obj))
        return perms

    def has_perm(self, user_obj, perm, obj=None):
        """
        Returns ``True`` if given ``user_obj`` has ``perm`` for ``obj``. If no
        ``obj`` is given, ``False`` is returned.

        .. note::

           Remember, that if user is not *active*, all checks would return
           ``False``.

        Main difference between Django's ``ModelBackend`` is that we can pass
        ``obj`` instance here and ``perm`` doesn't have to contain
        ``app_label`` as it can be retrieved from given ``obj``.

        **Inactive user support**

        If user is authenticated but inactive at the same time, all checks
        always returns ``False``.
        """
        if "." in perm and obj:
            app_label, codename = perm.split(".", maxsplit=1)
            if app_label != obj._meta.app_label:
                raise ValueError(
                    "Passed perm has app label of '%s' and " "given obj has '%s'" % (app_label, obj._meta.app_label)
                )

        if user_obj and not user_obj.is_active:
            return False
        elif user_obj and user_obj.is_superuser:
            return True
        return perm in self.get_all_permissions(user_obj, obj)

    def get_local_cache_key(self, obj):
        """
        Returns cache key for ``_obj_perms_cache`` dict.
        """
        ctype = ContentType.objects.get_for_model(obj)
        return (ctype.id, obj.pk)


class _LegacyTokenCheck(NamedTuple):
    is_dot_token: bool
    bypass_auth0: bool


_NOT_A_DOT_TOKEN: Final = _LegacyTokenCheck(is_dot_token=False, bypass_auth0=False)


class Auth0JWTAuthentication(BaseAuthentication):
    """
    Auth0 JWT authentication class that integrates with EarthRanger's tenant-aware system.

    This authentication backend:
    - Only activates when the tenant feature flag 'require_idp' is True
    - Uses the Auth0JWTBearerTokenValidator to validate JWT tokens
    - Maps Auth0 subject IDs to EarthRanger users via the auth0_id field
    """

    def __init__(self):
        self.keyword = "Bearer"
        self.resource_protector = ResourceProtector()
        self.resource_protector.register_token_validator(Auth0JWTBearerTokenValidator())

    @staticmethod
    def _get_bearer_token_value(request) -> str | None:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return None
        if not auth_header.startswith("Bearer "):
            return None
        parts = auth_header.split(" ", maxsplit=1)
        if len(parts) != 2:
            return None
        token_value = parts[1].strip()
        return token_value or None

    def _check_legacy_oauth2_token(self, request) -> _LegacyTokenCheck:
        """Classify the request's Bearer token as a legacy DOT token or not.

        Returns a _LegacyTokenCheck indicating whether the Bearer value is an opaque
        DOT token in our database and, if so, whether its application permits Auth0
        bypass. May raise AccessToken.MultipleObjectsReturned to surface data integrity issues.
        """
        token_value = self._get_bearer_token_value(request)
        if not token_value:
            return _NOT_A_DOT_TOKEN

        try:
            access_token = AccessToken.objects.select_related("application").get(token=token_value)
        except AccessToken.DoesNotExist:
            return _NOT_A_DOT_TOKEN

        if not access_token.application:
            return _NOT_A_DOT_TOKEN

        bypass = access_token.application.bypass_auth0
        if bypass:
            logger.debug(
                "Legacy DOT token for application %s has bypass_auth0=True", access_token.application.client_id
            )
        else:
            logger.warning(
                "Legacy DOT token for application %s has bypass_auth0=False", access_token.application.client_id
            )

        return _LegacyTokenCheck(is_dot_token=True, bypass_auth0=bypass)

    def authenticate(self, request):
        """
        Authenticate a request using Auth0 JWT tokens when IDP is required.

        Returns:
            - None: When require_idp=False (skip this authenticator), or when a legacy
              DOT token has bypass_auth0=True (allow fallback to OAuth2 authentication)
            - (AnonymousUser, None): When require_idp=True but no Authorization header
            - (User, None): When require_idp=True and valid Auth0 JWT token provided

        Raises:
            AuthenticationFailed: When require_idp=True and the token is invalid, the
                JWT sub claim is missing, or a DOT token has bypass_auth0=False
            APIException: When tenant settings cannot be resolved
            AccessToken.MultipleObjectsReturned: When duplicate DOT tokens exist
                (data integrity issue, surfaces as 500)
        """
        try:
            tenant_settings = get_tenant_settings()
            if not tenant_settings.feature_flags.require_idp:
                logger.debug(
                    "Auth0 authentication skipped because require_idp is False for tenant %s", tenant_settings.domain
                )
                return None
        except Exception as ex:
            logger.error("Cannot resolve tenant settings, so failing closed.\n%s", ex)
            raise APIException()  # 500

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            logger.debug("Auth0 authentication skipped because no authorization header")
            return AnonymousUser(), None

        # Carve-out: allow legacy OAuth2 clients whose application has bypass_auth0=True to keep
        # using DOT access tokens even when require_idp=True.
        token_check = self._check_legacy_oauth2_token(request)
        if token_check.is_dot_token:
            if token_check.bypass_auth0:
                return None  # Allow fallback to OAuth2 authentication.
            # Fail closed: a DOT token without bypass must not fall through to JWT
            # validation (which would reject it with a misleading "invalid JWT" error).
            raise AuthenticationFailed()

        # From here forward, we must either successfully return a user,
        # or fail authentication by raising, since `require_idp` must be True.

        try:
            token: JWTAccessTokenClaims = self.resource_protector.validate_request(scopes=None, request=request)
        except Exception:
            logger.exception("Auth0 JWT validation failed")
            raise AuthenticationFailed()

        auth0_subject = token.get("sub")
        if not auth0_subject:
            logger.warning("Auth0 JWT missing sub claim")
            raise AuthenticationFailed()

        try:
            user = User.objects.get(auth0_id=auth0_subject, is_active=True)
            user = _act_as_user_in_request(user, request)
            return user, None
        except User.DoesNotExist:
            logger.warning("Could not retrieve an active user with auth0_id %s", auth0_subject)
            raise AuthenticationFailed()
        except User.MultipleObjectsReturned:
            logger.error("Multiple active users found with auth0_id %s", auth0_subject)
            raise AuthenticationFailed()

    def authenticate_header(self, request):
        return self.keyword


class Auth0BackendForStaffUsers(BaseBackend):
    """
    Auth0 authentication backend for Django Admin staff users.

    This backend authenticates staff users via Auth0 OAuth2 tokens for Django Admin access.
    It enforces strict security requirements by only allowing active staff users with
    valid Auth0 IDs to authenticate.

    Security constraints:
    - User must exist in the database with a matching auth0_id
    - User must be active (is_active=True)
    - User must be staff (is_staff=True)

    Usage:
        This backend is designed to work with the Auth0 OAuth flow for Django Admin.
        It expects an OAuth2Token containing userinfo with an Auth0 subject ID.

    Authentication flow:
        1. Extract Auth0 subject ID from OAuth2 token userinfo
        2. Look up user by auth0_id and is_active=True
        3. Verify user has is_staff=True
        4. Return authenticated user or None

    Reference:
        https://community.auth0.com/t/implementing-auth0-in-django-admin/132271/3
    """

    def authenticate(self, request, token: OAuth2Token | None = None, **kwargs) -> User | None:
        # Only handle Auth0 token-based authentication
        if token is None:
            return None

        try:
            user_info = token.get("userinfo")
            auth0_id = user_info.get("sub")
        except Exception:
            logger.exception("Error occurred authenticating a staff user!")
            return None

        if not auth0_id:
            logger.warning("Auth0 staff token missing sub claim in userinfo")
            return None

        try:
            user = User.objects.get(auth0_id=auth0_id, is_active=True)
            if user.is_staff:
                return user
            else:
                logger.error(
                    "Non-staff user %s with auth0_id %s is attempting to authenticate as staff!",
                    user.username,
                    auth0_id,
                )
                return None
        except User.DoesNotExist:
            logger.warning("Could not retrieve an active staff user with auth0_id %s", auth0_id)
            return None
        except User.MultipleObjectsReturned:
            logger.error("Multiple active users found with auth0_id %s", auth0_id)
            return None

    def get_user(self, user_id) -> User | None:
        try:
            return User.objects.get(pk=user_id, is_active=True, is_staff=True)
        except User.DoesNotExist:
            logger.warning("Could not retrieve an active staff user with id %s", user_id)
            return None
