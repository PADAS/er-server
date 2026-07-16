from __future__ import annotations

import logging
import time
from typing import Callable, NamedTuple

from auth0.management import ManagementClient
from auth0.management.errors import ConflictError
from authlib.common.security import generate_token

from django.conf import settings

from utils.auth0.helpers import create_auth0_management_client
from utils.auth0.invariants import required
from utils.decorator import retry_on_exception

logger = logging.getLogger(__name__)


class AuthZeroUserProvisioningResult(NamedTuple):
    auth0_id: str
    password_reset_link: str | None


class AuthZeroUserProvisioner:
    """Provisioner to configure users in Auth0 for EarthRanger.

    Uses the v5 ManagementClient which handles token lifecycle internally.
    The client_factory default returns a process-wide cached instance that
    reuses the SDK's token cache and httpx connection pool.
    """

    def __init__(
        self,
        das_user_username: str,
        das_user_email: str | None,
        das_site_name: str,
        auth0_organization_id: str,
        client_factory: Callable[[], ManagementClient] = create_auth0_management_client,
    ):
        """Initialize provisioner to provision a single DAS user in Auth0.

        Args:
            das_user_username: EarthRanger username to provision in Auth0
            das_user_email: EarthRanger user's email (if any) to provision in Auth0
            das_site_name: EarthRanger site name used to
                            derive a fallback email address for use on provisioned Auth0 user
            auth0_organization_id: Auth0 opaque organization id to which the Auth0
                                    user should be added
            client_factory: Function that returns an Auth0 ManagementClient instance.
                          Defaults to the cached create_auth0_management_client factory.
        """
        self.auth0 = client_factory()
        self.auth0_organization_id = auth0_organization_id
        self.connection_name = getattr(settings, "AUTH0_USER_DB_CONNECTION_NAME")
        self.resolved_email_address = das_user_email or f"{das_user_username}.{das_site_name}@managed.pamdas.org"
        self.das_user_username = das_user_username

    def provision_user(self) -> AuthZeroUserProvisioningResult:
        is_newly_created = self._upsert_auth0_user()
        auth0_id = self._get_auth0_user_id_by_username()
        self._add_auth0_user_to_auth0_org(auth0_id)
        password_reset_link: str | None = None
        if is_newly_created:
            password_reset_link = self._create_password_change_ticket(auth0_id)
        return AuthZeroUserProvisioningResult(auth0_id=auth0_id, password_reset_link=password_reset_link)

    def _upsert_auth0_user(self) -> bool:
        try:
            self.auth0.users.create(
                connection=self.connection_name,
                password=generate_token(),
                username=self.das_user_username,
                email=self.resolved_email_address,
            )
            time.sleep(5)  # Auth0's api is eventually consistent
            return True
        except ConflictError:
            logger.warning("User '%s' already exists in Auth0", self.das_user_username)
            return False

    @retry_on_exception(ValueError, delay=5, max_retries=6)
    def _get_auth0_user_id_by_username(self) -> str:
        # auth0-python #856: users.list(include_totals=False) raises ParsingError on a
        # successful 200 because the SDK validates the bare-array response against the
        # dict-shaped ListUsersOffsetPaginatedResponseContent model. include_totals=True
        # is the only response shape the SyncPager can parse, so request it and iterate
        # the pager for the user items. https://github.com/auth0/auth0-python/issues/856
        matching_users = list(
            self.auth0.users.list(
                q=f'username:"{self.das_user_username}" AND identities.connection:"{self.connection_name}"',
                include_totals=True,
                fields="user_id",
            )
        )

        if not matching_users:
            raise ValueError(f"User '{self.das_user_username}' not found in Auth0 connection '{self.connection_name}'")

        if len(matching_users) > 1:
            raise ValueError(
                f"Multiple users found with username '{self.das_user_username}' in Auth0 connection '{self.connection_name}'"
            )

        return required(matching_users[0].user_id, field="user_id")

    def _add_auth0_user_to_auth0_org(self, auth0_id: str) -> None:
        self.auth0.organizations.members.create(self.auth0_organization_id, members=[auth0_id])

    def _create_password_change_ticket(self, auth0_id: str) -> str:
        result = self.auth0.tickets.change_password(user_id=auth0_id)
        return result.ticket
