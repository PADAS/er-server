import logging
from datetime import timedelta

from oauthlib.common import generate_token

from django.conf import settings
from django.utils import timezone

from core.models.oauth import DASAccessToken, DASApplication
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)

EFB_APPLICATION_ID = "EFB_APPLICATION_ID"
EFB_COOKIE_NAME = "efb_access_token"


def get_or_create_efb_token(user):
    """Return an existing valid EFB access token for the user, or create one.

    Returns None if the EFB OAuth2 application doesn't exist in this tenant
    or if token creation fails.
    """
    token = DASAccessToken.objects.filter(
        application__client_id=EFB_APPLICATION_ID,
        user=user,
        expires__gt=timezone.now(),
    ).first()

    if token:
        return token

    try:
        efb_app = DASApplication.objects.get(client_id=EFB_APPLICATION_ID)
    except DASApplication.DoesNotExist:
        logger.warning(
            "EFB application with client_id %s does not exist in tenant %s",
            EFB_APPLICATION_ID,
            get_tenant_settings().domain,
        )
        return None

    try:
        oauth2_settings = getattr(settings, "OAUTH2_PROVIDER", {})
        expire_in_secs = oauth2_settings.get("ACCESS_TOKEN_EXPIRE_SECONDS")
        expires = timezone.now() + timedelta(seconds=expire_in_secs)

        token = DASAccessToken.objects.create(
            user=user,
            token=generate_token(),
            application=efb_app,
            expires=expires,
            scope="read write",
            das_tenant=user.das_tenant,
        )
        logger.debug("Created EFB access token for user %s", user.username)
        return token

    except Exception as e:
        logger.error("Error creating EFB token: %s", e)
        return None


def set_efb_token_cookie(request, response):
    """Create or retrieve an EFB access token and set it as a cookie on the response.

    No-op if the user is not an authenticated staff member.
    """
    if not request.user.is_authenticated or not request.user.is_staff:
        return

    token = get_or_create_efb_token(request.user)
    if token:
        max_age = max(0, int((token.expires - timezone.now()).total_seconds()))
        response.set_cookie(
            EFB_COOKIE_NAME,
            token.token,
            samesite="Lax",
            secure=True,
            httponly=True,
            max_age=max_age,
            path="/",
        )
