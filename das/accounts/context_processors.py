from utils.tenant import get_tenant_settings


def eula_context_processor(request):
    return {"ACCEPT_EULA": get_tenant_settings().env_settings.accept_eula}
