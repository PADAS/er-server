import logging
import time
from typing import Callable, NamedTuple

from auth0.exceptions import Auth0Error
from auth0.management import Auth0
from authlib.common.security import generate_token

from django.conf import settings

from utils.auth0.helpers import (
    get_auth0_custom_domain,
    get_auth0_management_api_access_token,
)
from utils.decorator import retry_on_exception

logger = logging.getLogger(__name__)


class AuthZeroUserProvisioningResult(NamedTuple):
    auth0_id: str
    password_reset_link: str | None


class AuthZeroUserProvisioner:
    """Provisioner to configure users in Auth0 for EarthRanger.

    This class is designed to provision a single user to avoid token lifetime issues.
    Each instance should be created for one-time use.
    """

    def __init__(
        self,
        das_user_username: str,
        auth0_organization_id: str,
        token_factory: Callable[[], str] = get_auth0_management_api_access_token,
        auth0_factory: Callable[[str, str], Auth0] = Auth0,
    ):
        """Initialize provisioner with username, token factory, and Auth0 factory.

        Args:
            das_user_username: EarthRanger username to provision
            auth0_organization_id: Auth0 opaque organization id to which the Auth0
                                    user should be added,
            token_factory: Function that returns Auth0 management API access token
            auth0_factory: Function that takes (domain, token) and returns Auth0 client instance.
                          Defaults to Auth0 constructor.
        """
        domain = get_auth0_custom_domain()
        token = token_factory()

        self.auth0 = auth0_factory(domain, token)
        self.auth0_organization_id = auth0_organization_id
        self.connection_name = getattr(settings, "AUTH0_USER_DB_CONNECTION_NAME")
        self.das_username = das_user_username

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
                {
                    "connection": self.connection_name,
                    "password": generate_token(),
                    "username": self.das_username,
                }
            )
            time.sleep(5)  # Auth0's api is eventually consistent
            return True
        except Auth0Error as e:
            if e.status_code == 409:
                logger.warning("User '%s' already exists in Auth0", self.das_username)
                return False
            else:
                raise

    @retry_on_exception(ValueError, delay=5, max_retries=6)
    def _get_auth0_user_id_by_username(self) -> str:
        matching_users = self.auth0.users.list(
            q=f'username:"{self.das_username}" AND identities.connection:"{self.connection_name}"',
            include_totals=False,
            fields=["user_id"],
        )

        if not matching_users:
            raise ValueError(f"User '{self.das_username}' not found in Auth0 connection '{self.connection_name}'")

        if len(matching_users) > 1:
            raise ValueError(
                f"Multiple users found with username '{self.das_username}' in Auth0 connection '{self.connection_name}'"
            )

        return matching_users[0]["user_id"]

    def _add_auth0_user_to_auth0_org(self, auth0_id: str) -> None:
        self.auth0.organizations.create_organization_members(self.auth0_organization_id, {"members": [auth0_id]})

    def _create_password_change_ticket(self, auth0_id: str) -> str:
        result = self.auth0.tickets.create_pswd_change(
            {
                "user_id": auth0_id,
            }
        )
        return result["ticket"]
