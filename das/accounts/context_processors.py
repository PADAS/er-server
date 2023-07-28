from django.conf import settings

from utils.features import features
from utils.tenant import get_tenant_settings


def eula_context_processor(request):
    if features.tms.is_on():
        return {"ACCEPT_EULA": get_tenant_settings().env_settings.accept_eula}

    return {"ACCEPT_EULA": settings.ACCEPT_EULA}
