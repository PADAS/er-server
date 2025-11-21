import logging
import uuid

from oauth2_provider.backends import OAuth2Backend
from oauth2_provider.contrib.rest_framework.authentication import OAuth2Authentication

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication

from accounts.models import User
from accounts.utils import filter_permissions_by_tenant, parse_permission_codename
from utils.tenant import get_tenant_settings

logger = logging.getLogger("django.request")


def act_as_user_in_request(user, request):
    profile_header = request.META.get("HTTP_USER_PROFILE", None)
    if profile_header and user and not user.is_anonymous:
        logged_in_user = user
        profile_pk = uuid.UUID(profile_header)
        if profile_pk == logged_in_user.pk:
            message = "User Profile %s is the same as logged in user %s" % (profile_pk, logged_in_user.pk)
            logger.info(message)
            return user

        if 1 != logged_in_user.act_as_profiles.all().filter(pk=profile_pk).count():
            message = "User Profile %s not found in act_as_profiles list for user %s" % (profile_pk, logged_in_user.pk)
            logger.info(message)
            raise exceptions.PermissionDenied(message)

        profile_user = User.objects.get(pk=profile_pk)
        if profile_user.is_staff or profile_user.is_superuser:
            message = "User Profile %s is staff or superuser" % (profile_user.pk,)
            logger.info(message)
            raise exceptions.PermissionDenied(message)

        logger.info("User %s is acting as user %s.", logged_in_user.pk, profile_user.pk)
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

        return act_as_user_in_request(user, request)


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

        user = act_as_user_in_request(user, request)
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
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        has_bearer_token = auth_header.startswith(self.keyword + " ")

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

    def authenticate(self, request):
        # First, try OAuth2 token authentication
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        has_bearer_token = auth_header.startswith(self.keyword + " ")

        # DEBUG: Log what we're seeing
        request_method = getattr(request, "method", "UNKNOWN")
        request_path = getattr(request, "path", "UNKNOWN")
        has_session = hasattr(request, "session") and request.session and "_auth_user_id" in request.session
        logger.info(
            f"PriorityOAuth2SessionAuthentication.authenticate - "
            f"Method: {request_method}, Path: {request_path}, "
            f"Has Bearer: {has_bearer_token}, Has Session: {has_session}, "
            f"Auth Header: {auth_header[:20] if auth_header else 'None'}..."
        )

        try:
            oauth2_result = self.oauth2_auth.authenticate(request)
        except exceptions.AuthenticationFailed:
            # Re-raise AuthenticationFailed exceptions to get 401 status
            logger.info("OAuth2 authentication failed with AuthenticationFailed exception")
            raise

        if oauth2_result:
            # OAuth2 token found and valid, use it
            username = oauth2_result[0].username if oauth2_result[0] else "None"
            logger.info(f"OAuth2 authentication SUCCESS - User: {username}")
            return oauth2_result

        # Check if there was an OAuth2 error (e.g., expired token)
        oauth2_error = getattr(request, "oauth2_error", {})
        if oauth2_error and has_bearer_token:
            # If there's an OAuth2 error and we have a Bearer token, raise AuthenticationFailed
            logger.info(f"OAuth2 error with Bearer token present: {oauth2_error}")
            raise exceptions.AuthenticationFailed("Token is invalid or expired")

        # If a Bearer token was provided but OAuth2 authentication didn't succeed,
        # do NOT fall back to session authentication. This ensures Bearer tokens
        # take absolute priority over session cookies.
        if has_bearer_token:
            # Bearer token was provided but authentication failed
            # Don't fall back to session, return None to try next auth class
            logger.info("Bearer token present but OAuth2 auth returned None - NOT falling back to session")
            return None

        # Fall back to session authentication only if no Bearer token was provided
        # Handle both DRF request objects and Django WSGIRequest objects
        logger.info("No Bearer token - attempting session authentication fallback")
        if hasattr(request, "_request"):
            # This is a DRF request object, use parent's authenticate method
            session_result = super().authenticate(request)
            if session_result:
                username = session_result[0].username if session_result[0] else "None"
                logger.info(f"Session authentication SUCCESS - User: {username}")
            else:
                logger.info("Session authentication returned None")
            return session_result
        else:
            # This is a Django WSGIRequest object, check for session user directly
            user = getattr(request, "user", None)
            if user and user.is_authenticated and user.is_active:
                logger.info(f"Django session user found - User: {user.username}")
                return (user, None)
            logger.info("No authenticated Django session user")
            return None


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
                if obj and hasattr(obj, "get_obj_permission_set_ids"):
                    obj_ps_ids = obj.get_obj_permission_set_ids()
                    intersect_ids = user_ps_ids & obj_ps_ids

                    queryset = Permission.objects.filter(permission_sets__in=intersect_ids)
                else:
                    queryset = Permission.objects.filter(permission_sets__in=user_ps_ids)

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
