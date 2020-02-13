from django.conf import settings


def eula_context_processor(request):
    return {"ACCEPT_EULA": settings.ACCEPT_EULA,
            "EULA_REDIRECT": settings.EULA_REDIRECT}
