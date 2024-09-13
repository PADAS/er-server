from oauth2_provider.oauth2_validators import OAuth2Validator

from django.conf import settings


class ExtendExpiresInOAuth2Validator(OAuth2Validator):
    def save_bearer_token(self, token, request, *args, **kwargs):
        oauth2_settings = getattr(settings, "OAUTH2_PROVIDER", {})
        expire_overrides = oauth2_settings.get("EXPIRE_OVERRIDES", {})
        if request.client_id in expire_overrides:
            token["expires_in"] = int(expire_overrides[request.client_id])
        super().save_bearer_token(token, request, *args, **kwargs)
