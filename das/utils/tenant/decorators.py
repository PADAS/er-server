import functools
import logging
from typing import Callable

from django.http import HttpRequest, HttpResponse

from utils.features import features
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)


def append_tenant_domain(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if features.tms.is_on():
            kwargs["domain"] = get_tenant_settings().domain
        return func(*args, **kwargs)

    return wrapper


class IdpNotConfiguredError(Exception):
    """Raised when tenant IdP feature flags are not properly configured."""


def assert_idp_configured() -> None:
    """Check that the tenant has IdP enabled with an org ID configured.

    Raises IdpNotConfiguredError if require_idp is falsy or idp_org_id is missing.
    """
    ts = get_tenant_settings()
    problems = []
    if not ts.feature_flags.require_idp:
        problems.append("require_idp is not enabled")
    org_id = ts.feature_flags.idp_org_id
    if not org_id or not org_id.strip():
        problems.append("idp_org_id is not configured")
    if problems:
        raise IdpNotConfiguredError(f"tenant {ts.id}: {'; '.join(problems)}")


ViewFunc = Callable[..., HttpResponse]


def require_enabled_idp_configs(*, message: str, status: int) -> Callable[[ViewFunc], ViewFunc]:
    """View decorator that returns an error response if IdP is not configured.

    Usage:
        @require_enabled_idp_configs(message="...", status=400)
    """

    def decorator(view_func: ViewFunc) -> ViewFunc:
        @functools.wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            try:
                assert_idp_configured()
            except IdpNotConfiguredError as e:
                logger.error("IdP not configured for tenant: %s", e)
                return HttpResponse(message, status=status)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
