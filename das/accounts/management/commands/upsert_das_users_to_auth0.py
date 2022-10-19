from typing import Callable, List, NamedTuple, Protocol, Union
from urllib.parse import urlparse

from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from utils.auth0.client import AuthZeroUserProvisioner, AuthZeroUserProvisioningResult
from utils.auth0.helpers import get_auth0_management_api_access_token
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin


class _DasUserToAuth0ProvisioningSuccess(NamedTuple):
    das_user_username: str
    password_reset_link: str | None


class _DasUserToAuth0ProvisioningFailure(NamedTuple):
    das_user_username: str
    exception_message: str


_DasUserToAuth0ProvisioningResult = Union[_DasUserToAuth0ProvisioningSuccess, _DasUserToAuth0ProvisioningFailure]


class ProvisionerFactory(Protocol):
    def __call__(
        self,
        *,
        das_user_username: str,
        das_user_email: str | None,
        das_site_name: str,
        auth0_organization_id: str,
        token_factory: Callable[[], str],
        auth0_factory: Callable[[str, str], object] = ...,
    ) -> AuthZeroUserProvisioner: ...


class Command(TenantCommandMixin, BaseCommand):
    help = "Upsert DAS users to Auth0 for a specific tenant domain"

    # List of usernames that should not be provisioned to Auth0
    DISALLOWED_USERNAMES = ["er_system", "admin"]

    def __init__(
        self,
        provisioner_factory: ProvisionerFactory = AuthZeroUserProvisioner,
        token_factory: Callable[[], str] = get_auth0_management_api_access_token,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.provisioner_factory = provisioner_factory
        self.token = token_factory()

    def handle(self, *args, **options) -> None:
        tenant_settings = get_tenant_settings()
        auth0_org_id = tenant_settings.feature_flags.idp_org_id
        full_tenant_domain = f"https://{tenant_settings.domain}"

        if auth0_org_id is None:
            raise CommandError("idp_org_id is not configured in tenant feature flags")

        hostname = urlparse(full_tenant_domain).hostname
        if not hostname:
            raise CommandError(f"Cannot extract site name from {tenant_settings.domain}")

        domain_parts = hostname.split(".")
        if len(domain_parts) < 3:
            raise CommandError(f"Cannot extract site name from {tenant_settings.domain}")

        site_name = domain_parts[0]

        results = self._handle(auth0_org_id, site_name)
        successes = [r for r in results if isinstance(r, _DasUserToAuth0ProvisioningSuccess)]
        failures = [r for r in results if isinstance(r, _DasUserToAuth0ProvisioningFailure)]
        self._output_results(successes)
        self._output_errors(failures)

        if failures:
            raise CommandError(f"Failed to provision {len(failures)} users!")

    @transaction.atomic
    def _handle(self, auth0_org_id: str, site_name: str) -> List[_DasUserToAuth0ProvisioningResult]:
        users = User.objects.filter(is_active=True).exclude(username__in=self.DISALLOWED_USERNAMES)

        results: List[_DasUserToAuth0ProvisioningResult] = []
        for user in users:
            current_username = user.username
            user_email = user.email
            current_auth0_id = user.auth0_id
            try:
                result = self._provision_user_in_auth0(
                    das_user_username=current_username,
                    das_user_email=user_email,
                    site_name=site_name,
                    auth0_org_id=auth0_org_id,
                )

                if current_auth0_id and current_auth0_id != result.auth0_id:
                    results.append(
                        _DasUserToAuth0ProvisioningFailure(
                            das_user_username=current_username,
                            exception_message=f"User {current_username} already has auth0_id '{current_auth0_id}' "
                            f"but Auth0 returned '{result.auth0_id}'",
                        )
                    )
                else:
                    user.auth0_id = result.auth0_id
                    user.save(update_fields=["auth0_id"])
                    results.append(
                        _DasUserToAuth0ProvisioningSuccess(
                            das_user_username=current_username, password_reset_link=result.password_reset_link
                        )
                    )

            except Exception as ex:
                results.append(
                    _DasUserToAuth0ProvisioningFailure(das_user_username=current_username, exception_message=str(ex))
                )

        return results

    def _provision_user_in_auth0(
        self, das_user_username: str, das_user_email: str | None, site_name: str, auth0_org_id: str
    ) -> AuthZeroUserProvisioningResult:
        provisioner = self.provisioner_factory(
            das_user_username=das_user_username,
            das_user_email=das_user_email,
            das_site_name=site_name,
            auth0_organization_id=auth0_org_id,
            token_factory=lambda: self.token,
        )
        return provisioner.provision_user()

    def _output_errors(self, errors: List[_DasUserToAuth0ProvisioningFailure]) -> None:
        if errors:
            self.stdout.write(self.style.ERROR("FAILED TO PROVISION:"))
            error_lines = [f"{error.das_user_username}\t{error.exception_message}" for error in errors]
            self.stdout.write(self.style.ERROR("\n".join(error_lines)))

    def _output_results(self, results: List[_DasUserToAuth0ProvisioningSuccess]) -> None:
        if results:
            self.stdout.write("SUCCESSFULLY PROVISIONED:")
            result_lines = [f"{result.das_user_username}\t{result.password_reset_link}" for result in results]
            self.stdout.write("\n".join(result_lines))
