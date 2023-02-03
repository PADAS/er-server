from django.conf import settings

from utils.features import features
from utils.tenant import get_tenant_settings


def eula_context_processor(request):
    ACCEPT_EULA = get_tenant_settings().env_settings.accept_eula if features.tms.is_on() else settings.ACCEPT_EULA
    return {"ACCEPT_EULA": ACCEPT_EULA}
